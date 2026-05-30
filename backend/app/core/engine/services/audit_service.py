"""
AuditService — Three-tier finish auditing extracted from FinishNode.

Encapsulates:
  - Tier classification (minimal / standard / comprehensive)
  - Rule-based minimal audit
  - LLM-based standard audit
  - Full engine-driven comprehensive audit

This module has NO runtime side effects at import time (lazy-init pattern).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic import Field

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager
from app.core.engine.message.reasoning import extract_tool_calls
from app.core.engine.state import AgentState
from app.core.engine.state.blackboard import BlackboardState, VerificationStatus
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------

class AuditDecision(DynamicBaseModel):
    """Decision for audit tier selection."""
    tier: str
    reason: str
    confidence: float


class AuditResult(DynamicBaseModel):
    """Result of an audit execution."""
    summary: str
    tier: str
    meta: dict
    messages: list = Field(default_factory=list)
    blackboard: BlackboardState | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_tool_usage(messages: list) -> str:
    """Extract structured tool usage summary from messages."""
    tool_msgs = []
    for msg in messages:
        for tc in extract_tool_calls(msg):
            name = tc.get("name")
            if name:
                args = tc.get("args")
                arg_str = str(args)[:200] if args else ""
                tool_msgs.append(f"  - {name}: {arg_str}")
    return "\n".join(tool_msgs) if tool_msgs else "No tools used."


def _extract_final_summary(messages: list) -> str:
    """Extract the final assistant message for summary."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            content = str(msg.content)
            if "<evoloop_session_audit>" in content and "<evoloop_final_report>" in content:
                match = re.search(
                    r"<evoloop_final_report>(.*?)</evoloop_final_report>",
                    content,
                    re.IGNORECASE | re.DOTALL,
                )
                if match:
                    return match.group(1).strip()
            return content
    return "Task completed."


# ---------------------------------------------------------------------------
# LayeredAuditor
# ---------------------------------------------------------------------------

class LayeredAuditor:
    """Three-tier finish auditor with quality preservation."""

    READONLY_TOOLS = frozenset({
        "read_file", "list_directory", "get_file_info", "search_files",
        "analyze_image", "search_web", "read_url_content",
        "search_history", "search_skills",
    })

    FILE_WRITE_TOOLS = frozenset({
        "write_file", "edit_file", "delete_file", "move_file", "create_directory",
    })

    EXECUTION_TOOLS = frozenset({
        "execute_command", "bash", "shell", "python",
    })

    AUTOMATION_TOOLS = frozenset({
        "mobile_control", "browser_control", "desktop_control",
        "open_app", "click_at", "type_text", "press_key",
    })

    ERROR_PATTERNS = [
        r"\[ERROR:", r"^Error:", r"Exception:", r"Traceback",
        r"Failed to", r"Permission denied", r"File not found",
    ]

    # ------------------------------------------------------------------
    # Tier classification
    # ------------------------------------------------------------------

    def classify_tier(
        self,
        tool_history: list,
        messages: list,
        blackboard: BlackboardState,
        state: AgentState,
    ) -> AuditDecision:
        """Classify which audit tier is appropriate."""
        used_tools = set()
        for sig in tool_history:
            tool_name = sig.split(":")[0] if ":" in sig else sig
            used_tools.add(tool_name)

        last_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_content = str(msg.content)
                break

        triggers = []

        if used_tools & self.FILE_WRITE_TOOLS:
            triggers.append("file_modification")
        if used_tools & self.EXECUTION_TOOLS:
            triggers.append("code_execution")
        if used_tools & self.AUTOMATION_TOOLS:
            triggers.append("ui_automation")

        for pattern in self.ERROR_PATTERNS:
            if re.search(pattern, last_content, re.MULTILINE):
                triggers.append("error_detected")
                break

        ticket = state.blackboard.ticket
        if ticket and ticket.complexity == "high":
            triggers.append("high_complexity")

        verification = blackboard.verification
        if verification and verification.status in ("failed", "error"):
            triggers.append("verification_failed")

        if len(messages) > 50:
            triggers.append("long_conversation")

        # NEW: Check for audit anomalies flagged by intermediate layers
        anomalies = blackboard.metadata.audit_anomalies if blackboard and blackboard.metadata else []
        if anomalies:
            triggers.append("anomalies_detected")

        # Worker 使用了技能（通过路由下发的 skill_ids）
        if blackboard and blackboard.ticket and blackboard.ticket.skill_ids:
            triggers.append("skill_used")

        # Supervisor 定义过规划
        has_plan = bool(state.current_plan or state.structured_plan)
        has_plan_progress = (
            blackboard and blackboard.metadata and blackboard.metadata.plan_progress
            and blackboard.metadata.plan_progress.total_steps > 0
        )
        if has_plan or has_plan_progress:
            triggers.append("plan_defined")

        if triggers:
            logger.info(f"[AuditService] 🚩 Comprehensive triggers: {triggers}")
            return AuditDecision(tier="comprehensive", reason=f"safety: {', '.join(triggers)}", confidence=1.0)

        return AuditDecision(tier="standard", reason="default", confidence=0.90)

    # ------------------------------------------------------------------
    # Standard audit — lightweight LLM, ~500–800 ms
    # ------------------------------------------------------------------

    async def audit_standard(
        self,
        messages: list,
        blackboard: BlackboardState,
        state: AgentState,
        config: RunnableConfig,
    ) -> tuple[str, dict]:
        start = time.time()

        tool_usage = []
        for msg in messages:
            for tc in extract_tool_calls(msg):
                name = tc.get("name")
                if name:
                    tool_usage.append(name)

        last_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_content = str(msg.content)
                break

        from app.core.engine.prompts import FinishPromptBuilder

        builder = FinishPromptBuilder(
            current_plan=state.current_plan or "",
            execution_ticket=blackboard.ticket,
            verification_status=blackboard.verification,
            action_context=_extract_tool_usage(messages),
            iteration_count=state.iteration_count or 0,
            project_id=state.project_id if state.project_id is not None else DEFAULT_PROJECT_ID,
            blackboard=blackboard,
            session_goal=state.session_goal,
        )
        prompt = builder.build_standard_prompt(last_content, list(set(tool_usage)))

        from app.core.llm import InternalLLMService
        from app.infrastructure.config.service import SystemConfigService
        model_name = SystemConfigService.get_value("LLM_MODEL")
        try:
            response = await asyncio.wait_for(
                InternalLLMService.invoke(
                    messages=[{"role": "system", "content": prompt}],
                    purpose="audit_summary",
                    temperature=0.1,
                    max_tokens=500,
                    model_name=model_name,
                ),
                timeout=30.0
            )
            summary = response.content.strip()
        except asyncio.TimeoutError:
            logger.warning("[AuditService] Standard audit LLM call timed out after 30s. Using fallback summary.")
            summary = "Task completed (audit timed out)."
        except Exception as e:
            logger.error(f"[AuditService] Standard audit LLM call failed: {e}")
            summary = "Task completed (audit failed)."
        if len(summary) < 20:
            summary = f"Task completed. {summary}"

        duration = (time.time() - start) * 1000
        return summary, {"tier": "standard", "duration_ms": duration}

    # ------------------------------------------------------------------
    # Helpers for structured audit input
    # ------------------------------------------------------------------

    def _build_audit_input(self, state: AgentState) -> dict:
        """Build structured audit input from blackboard instead of full messages."""
        blackboard = state.blackboard
        metadata = blackboard.metadata if blackboard else None
        audit_input_data = metadata.audit_input_data if metadata else None

        if audit_input_data:
            # Use pre-built structured audit input if available
            return audit_input_data.model_dump()

        # Fallback: build from blackboard metadata
        plan_progress = metadata.plan_progress if metadata else None

        # Build tool stats from tool_history
        tool_stats: dict[str, int] = {}
        for sig in metadata.tool_history or []:
            tool_name = sig.split(":")[0] if ":" in sig else sig
            tool_stats[tool_name] = tool_stats.get(tool_name, 0) + 1

        progress = {
            "total_steps": plan_progress.total_steps if plan_progress else 0,
            "completed_steps": plan_progress.completed_steps if plan_progress else 0,
            "total_deliverables": len(metadata.audit_input_data.deliverables) if metadata and metadata.audit_input_data else 0,
            "completed_deliverables": 0,
        }

        return {
            "original_goal": state.session_goal or "",
            "plan_summary": {
                "total": plan_progress.total_steps if plan_progress else 0,
                "completed": plan_progress.completed_steps if plan_progress else 0,
                "remaining": (plan_progress.total_steps - plan_progress.completed_steps) if plan_progress else 0,
            },
            "progress": progress,
            "deliverables": [],
            "tool_stats": tool_stats,
            "anomalies": [a.model_dump() for a in (metadata.audit_anomalies if metadata else [])],
            "key_messages_digest": "",
        }

    # ------------------------------------------------------------------
    # Comprehensive audit — full engine-driven
    # ------------------------------------------------------------------

    async def audit_comprehensive(
        self,
        state: AgentState,
        config: RunnableConfig,
    ) -> AuditResult:
        """Run the full engine-driven comprehensive audit.

        Phase 1 improvement: Uses structured AuditInputData when available,
        reducing context from ~18K tokens (full messages) to ~500 tokens.
        Falls back to legacy full-message mode if structured data is absent.
        """
        from app.core.config import settings
        from app.core.engine.prompts import FinishPromptBuilder

        ctx = ContextManager.current()
        messages = list(state.messages)
        blackboard = state.blackboard

        current_plan = state.current_plan or ""
        execution_ticket = state.blackboard.ticket
        verification_status = blackboard.verification or VerificationStatus(status="unverified")
        action_context = _extract_tool_usage(messages)
        iteration_count = state.iteration_count or 0
        project_id = ctx.project_id if ctx.project_id is not None else (state.project_id if state.project_id is not None else DEFAULT_PROJECT_ID)

        from app.core.environment import get_awakened_state
        awakened_state = get_awakened_state()
        telemetry: dict[str, Any] = {}
        if awakened_state:
            try:
                telemetry_snapshot = awakened_state.get_telemetry_snapshot()
                if telemetry_snapshot:
                    telemetry = telemetry_snapshot.model_dump()
            except Exception as e:
                logger.warning(f"[AuditService] Telemetry snapshot failed: {e}")

        # Phase 1: Build structured audit input
        audit_input = self._build_audit_input(state)
        has_structured_input = bool(
            blackboard.metadata and blackboard.metadata.audit_input_data
        )

        builder = FinishPromptBuilder(
            current_plan=current_plan,
            execution_ticket=execution_ticket,
            verification_status=verification_status,
            action_context=action_context,
            iteration_count=iteration_count,
            project_id=project_id,
            telemetry=telemetry,
            blackboard=blackboard,
            session_goal=state.session_goal,
        )
        system_prompt = builder.build()
        audit_ticket = builder.build_audit_ticket()

        # Phase 1: Inject structured audit input into audit ticket if available
        if has_structured_input and audit_ticket:
            audit_input_json = json.dumps(audit_input, indent=2, ensure_ascii=False)
            audit_ticket = f"{audit_ticket}\n\n---\n📊 Structured Audit Input:\n{audit_input_json}"

        from app.core.tools.manager import tool_manager
        tools = await tool_manager.get_node_tools("finish", state)

        logger.info("[AuditService] 🕵️ Starting Comprehensive Audit")

        if audit_ticket:
            from langchain_core.messages import HumanMessage
            messages = [HumanMessage(content=audit_ticket, name="audit_ticket")] + messages

        # Phase 1: If structured input is available, truncate older messages to reduce context
        if has_structured_input and len(messages) > 25:
            # Keep audit_ticket + last 10 messages + first 2 messages (for context)
            preserved = messages[:3] + messages[-12:]
            logger.info(f"[AuditService] 📉 Truncated audit context: {len(messages)} → {len(preserved)} msgs (structured input available)")
            messages = preserved

        # Clone and sanitize config to avoid database logging and SSE stream leaks from audit
        clean_config = dict(config or {})
        if "callbacks" in clean_config:
            callbacks = clean_config["callbacks"]
            if isinstance(callbacks, list):
                clean_config["callbacks"] = [
                    cb for cb in callbacks
                    if cb.__class__.__name__ not in ("DatabaseCallbackHandler", "TransparentCallbackHandler")
                ]

        execution_state = state.model_copy(update={"messages": messages})
        model = clean_config.get("configurable", {}).get("model")

        from app.core.engine.engine import get_default_engine
        engine = get_default_engine()
        result = await engine.run_node(
            state=execution_state,
            config=clean_config,
            system_prompt=system_prompt,
            tools=tools,
            model=model,
            name="Session Reviewer",
            max_steps=settings.FINISH_AGENT_MAX_STEPS,
            node_source="finish",
        )

        summary = _extract_final_summary(result.messages or [])
        return AuditResult(
            summary=summary,
            tier="comprehensive",
            meta={"tier": "comprehensive", "duration_ms": 0},
            messages=result.messages or [],
            blackboard=result.blackboard,
        )


# ---------------------------------------------------------------------------
# Singleton accessor (lazy)
# ---------------------------------------------------------------------------

_auditor_instance: LayeredAuditor | None = None


def get_auditor() -> LayeredAuditor:
    global _auditor_instance
    if _auditor_instance is None:
        _auditor_instance = LayeredAuditor()
    return _auditor_instance


def reset_auditor() -> None:
    """Reset the global auditor singleton (useful in tests)."""
    global _auditor_instance
    _auditor_instance = None


# ---------------------------------------------------------------------------
# Service facade
# ---------------------------------------------------------------------------

class AuditService:
    """
    High-level facade for the three-tier audit system.
    """

    def __init__(self, auditor: LayeredAuditor | None = None):
        self._auditor = auditor or get_auditor()

    async def execute(
        self,
        state: AgentState,
        config: RunnableConfig,
        tool_history: list,
        is_shadow_mode: bool = False,
    ) -> AuditResult:
        """
        Run the full audit pipeline and return an AuditResult.
        """
        if is_shadow_mode:
            summary = _extract_final_summary(state.messages)
            return AuditResult(
                summary=summary,
                tier="shadow",
                meta={"tier": "shadow", "duration_ms": 10},
            )

        decision = self._auditor.classify_tier(
            tool_history, state.messages, state.blackboard, state
        )
        tier = decision.tier

        logger.info(f"[AuditService] Audit tier: {tier.upper()} ({decision.reason})")

        if tier == "standard":
            summary, meta = await self._auditor.audit_standard(
                state.messages, state.blackboard, state, config
            )
            return AuditResult(summary=summary, tier=tier, meta=meta)

        # comprehensive
        return await self._auditor.audit_comprehensive(state, config)
