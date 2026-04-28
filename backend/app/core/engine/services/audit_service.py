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

import logging
import re
import time

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager
from app.core.engine.state import AgentState
from app.core.engine.state.blackboard import BlackboardState, VerificationStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_tool_usage(messages: list) -> str:
    """Extract structured tool usage summary from messages."""
    tool_msgs = []
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if name:
                    args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", None)
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
# Domain objects
# ---------------------------------------------------------------------------

class AuditDecision:
    """Decision for audit tier selection."""

    def __init__(self, tier: str, reason: str, confidence: float):
        self.tier = tier
        self.reason = reason
        self.confidence = confidence


class AuditResult:
    """Result of an audit execution."""

    def __init__(
        self,
        summary: str,
        tier: str,
        meta: dict,
        messages: list | None = None,
        blackboard: "BlackboardState" | None = None,
    ):
        self.summary = summary
        self.tier = tier
        self.meta = meta
        self.messages = messages or []
        self.blackboard = blackboard


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
        blackboard: "BlackboardState",
        state: "AgentState",
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

        if len(messages) > 20:
            triggers.append("long_conversation")

        if triggers:
            return AuditDecision("comprehensive", f"safety: {', '.join(triggers)}", 1.0)

        minimal_ok = [
            used_tools.issubset(self.READONLY_TOOLS),
            len(last_content) > 50,
            len(last_content) < 3000,
            not any(re.search(p, last_content) for p in self.ERROR_PATTERNS),
            not state.is_subtask,
        ]

        if all(minimal_ok):
            return AuditDecision("minimal", "readonly_safe", 0.95)

        return AuditDecision("standard", "default", 0.90)

    # ------------------------------------------------------------------
    # Minimal audit — rule-based, <10 ms
    # ------------------------------------------------------------------

    async def audit_minimal(
        self,
        messages: list,
        blackboard: "BlackboardState",
    ) -> tuple[str, dict]:
        last_content = ""
        tool_usage = []

        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_content = str(msg.content)
                break

        if not last_content:
            from langchain_core.messages import ToolMessage
            for msg in reversed(messages):
                if isinstance(msg, ToolMessage) and msg.content:
                    last_content = str(msg.content)
                    break

        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    if name:
                        tool_usage.append(name)

        max_len = 2000
        summary = last_content[:max_len] if len(last_content) <= max_len else last_content[:max_len] + "\n\n[Truncated]"

        return summary, {"tier": "minimal", "duration_ms": 5, "tools": list(set(tool_usage))}

    # ------------------------------------------------------------------
    # Standard audit — lightweight LLM, ~500–800 ms
    # ------------------------------------------------------------------

    async def audit_standard(
        self,
        messages: list,
        blackboard: "BlackboardState",
        state: "AgentState",
        config: "RunnableConfig",
    ) -> tuple[str, dict]:
        start = time.time()

        tool_usage = []
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    if name:
                        tool_usage.append(name)

        last_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_content = str(msg.content)
                break

        # Lazy import to avoid circular deps and heavy init at import time
        from app.core.engine.prompts import FinishPromptBuilder

        builder = FinishPromptBuilder(
            current_plan=state.current_plan or "",
            execution_ticket=blackboard.ticket,
            verification_status=blackboard.verification,
            action_context=_extract_tool_usage(messages),
            iteration_count=state.iteration_count or 0,
            project_id=state.project_id or DEFAULT_PROJECT_ID,
            blackboard=blackboard,
            session_goal=state.session_goal,
        )
        prompt = builder.build_standard_prompt(last_content, list(set(tool_usage)))

        try:
            from app.core.llm import InternalLLMService
            from app.infrastructure.config.service import SystemConfigService
            model_name = SystemConfigService.get_value("LLM_MODEL")
            response = await InternalLLMService.invoke(
                messages=[{"role": "system", "content": prompt}],
                purpose="audit_summary",
                temperature=0.1,
                max_tokens=500,
                model_name=model_name,
            )
            summary = str(response.content).strip() if hasattr(response, "content") else str(response).strip()
            if len(summary) < 20:
                summary = f"Task completed. {summary}"
        except Exception as e:
            logger.error(f"[Auditor] Standard audit failed: {e}")
            summary = f"Task completed.\n\n{last_content[:1000]}"

        duration = (time.time() - start) * 1000
        return summary, {"tier": "standard", "duration_ms": duration}

    # ------------------------------------------------------------------
    # Comprehensive audit — full engine-driven
    # ------------------------------------------------------------------

    async def audit_comprehensive(
        self,
        state: "AgentState",
        config: "RunnableConfig",
    ) -> AuditResult:
        """Run the full engine-driven comprehensive audit."""
        from app.core.engine.prompts import FinishPromptBuilder
        from app.core.config import settings

        ctx = ContextManager.current()
        messages = list(state.messages)
        blackboard = state.blackboard

        current_plan = state.current_plan or ""
        execution_ticket = state.blackboard.ticket
        verification_status = blackboard.verification or VerificationStatus(status="unverified")
        action_context = _extract_tool_usage(messages)
        iteration_count = state.iteration_count or 0
        project_id = ctx.project_id or state.project_id or DEFAULT_PROJECT_ID

        # Lazy import to avoid circular deps
        from app.core.environment import get_awakened_state
        env_state = get_awakened_state()
        telemetry_data = {}
        if env_state:
            telemetry_data = env_state.get_telemetry_snapshot()

        builder = FinishPromptBuilder(
            current_plan=current_plan,
            execution_ticket=execution_ticket,
            verification_status=verification_status,
            action_context=action_context,
            iteration_count=iteration_count,
            project_id=project_id,
            telemetry=telemetry_data,
            blackboard=blackboard,
            session_goal=state.session_goal,
        )
        system_prompt = builder.build()
        audit_ticket = builder.build_audit_ticket()

        from app.core.tools.manager import tool_manager
        tools = await tool_manager.get_node_tools("finish", state)

        logger.info("[AuditService] 🕵️ Starting Comprehensive Audit")

        if audit_ticket:
            from langchain_core.messages import HumanMessage
            messages = [HumanMessage(content=audit_ticket, name="audit_ticket")] + messages

        execution_state = state.model_copy(update={"messages": messages})
        model = config.get("configurable", {}).get("model")

        from app.core.engine.engine import get_default_engine
        engine = get_default_engine()
        result = await engine.run_node(
            state=execution_state,
            config=config,
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

    Usage:
        service = AuditService()
        result = await service.execute(state, config, tool_history, is_shadow_mode)
    """

    def __init__(self, auditor: LayeredAuditor | None = None):
        self._auditor = auditor or get_auditor()

    async def execute(
        self,
        state: "AgentState",
        config: "RunnableConfig",
        tool_history: list,
        is_shadow_mode: bool = False,
    ) -> AuditResult:
        """
        Run the full audit pipeline and return an AuditResult.

        * Shadow mode   → skip all auditing, return raw summary.
        * Minimal       → rule-based fast path.
        * Standard      → lightweight LLM audit.
        * Comprehensive → full engine-driven audit.
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

        if tier == "minimal":
            summary, meta = await self._auditor.audit_minimal(state.messages, state.blackboard)
            return AuditResult(summary=summary, tier=tier, meta=meta)

        if tier == "standard":
            summary, meta = await self._auditor.audit_standard(
                state.messages, state.blackboard, state, config
            )
            return AuditResult(summary=summary, tier=tier, meta=meta)

        # comprehensive
        return await self._auditor.audit_comprehensive(state, config)
