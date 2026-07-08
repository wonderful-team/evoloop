"""Unified audit — engine-driven Session Reviewer agent (no tier classification)."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from pydantic import Field

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager
from app.core.engine.engine import get_default_engine
from app.core.engine.message.native_classes import (
    HumanMessage,
    RunnableConfig,
)
from app.core.engine.message.reasoning import extract_tool_calls
from app.core.engine.state import AgentState
from app.core.engine.state.sub_schemas import VerificationStatus
from app.core.environment import get_awakened_state
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


def _role(msg):
    return msg.type


class AuditResult(DynamicBaseModel):
    """Result of an audit execution."""
    summary: str
    meta: dict = Field(default_factory=dict)
    messages: list = Field(default_factory=list)


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
    from app.core.engine.message.utils import get_message_text

    for msg in reversed(messages):
        role = _role(msg)
        if role in ("assistant", "ai"):
            content = get_message_text(msg)
            if content:
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


def _build_audit_input(state: AgentState) -> dict:
    if state.audit_input_data:
        return state.audit_input_data.model_dump()

    plan_progress = state.plan_progress

    # Build tool stats from tool_history
    tool_stats: dict[str, int] = {}
    for sig in state.tool_history or []:
        tool_name = sig.split(":")[0] if ":" in sig else sig
        tool_stats[tool_name] = tool_stats.get(tool_name, 0) + 1

    progress = {
        "total_steps": plan_progress.total_steps if plan_progress else 0,
        "completed_steps": plan_progress.completed_steps if plan_progress else 0,
        "total_deliverables": len(state.audit_input_data.deliverables) if state.audit_input_data and state.audit_input_data.deliverables else 0,
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
        "anomalies": [a.model_dump() for a in (state.audit_anomalies or [])],
        "key_messages_digest": "",
    }


class AuditService:
    """Unified engine-driven audit — Session Reviewer agent with tools + background extraction."""

    def __init__(self):
        pass

    async def execute(
        self,
        state: AgentState,
        config: RunnableConfig,
        tool_history: list,
        is_shadow_mode: bool = False,
    ) -> AuditResult:
        if is_shadow_mode:
            summary = _extract_final_summary(state.messages)
            return AuditResult(summary=summary, meta={"duration_ms": 10})

        from app.core.config import settings
        from app.core.engine.nodes.prompts import FinishPromptBuilder

        start = time.time()

        ctx = ContextManager.current()
        messages = state.messages

        current_plan = state.current_plan or ""
        execution_ticket = state.ticket
        verification_status = state.verification or VerificationStatus(status="unverified")
        action_context = _extract_tool_usage(messages)
        iteration_count = state.iteration_count or 0
        project_id = (
            ctx.project_id
            if ctx.project_id is not None
            else (state.project_id if state.project_id is not None else DEFAULT_PROJECT_ID)
        )

        awakened_state = get_awakened_state()
        telemetry: dict[str, Any] = {}
        if awakened_state:
            try:
                snapshot = awakened_state.get_telemetry_snapshot()
                if snapshot:
                    telemetry = snapshot.model_dump()
            except (AttributeError, ValueError, TypeError) as e:
                logger.warning(f"[AuditService] Telemetry snapshot failed: {e}")

        builder = FinishPromptBuilder(
            current_plan=current_plan,
            execution_ticket=execution_ticket,
            verification_status=verification_status,
            action_context=action_context,
            iteration_count=iteration_count,
            project_id=project_id,
            telemetry=telemetry,
            metadata=state.metadata,
            subtask_results=state.subtask_results,
            session_goal=state.session_goal,
        )
        system_prompt = builder.build()
        audit_ticket = builder.build_audit_ticket()

        # Build structured audit input to inject into audit ticket
        audit_input = _build_audit_input(state)
        has_structured_input = bool(
            state.audit_input_data
        )
        if has_structured_input and audit_ticket:
            audit_input_json = json.dumps(audit_input, indent=2, ensure_ascii=False)
            audit_ticket = f"{audit_ticket}\n\n---\n📊 Structured Audit Input:\n{audit_input_json}"

        from app.core.tools.manager import tool_manager
        tools = await tool_manager.get_node_tools("finish", state)

        logger.info("[AuditService] 🕵️ Starting engine-driven audit")

        if audit_ticket:
            messages = [HumanMessage(content=audit_ticket, name="audit_ticket")] + messages

        model = config.get("configurable", {}).get("model")

        # 1. Prepare Extraction Messages (Deep Semantic History)
        # We use ContextTrimmer to replace fat ToolMessages with placeholders, while keeping all reasoning.
        from app.core.engine.context_trimmer import ContextTrimmer
        trimmer = ContextTrimmer()
        # model parameter isn't strict here since we just want the semantic compaction, we use the active model
        extraction_trim_result = trimmer.trim(
            messages=messages,
            model=model,
            node_source="finish",
            stages={"window"}
        )
        extraction_messages = extraction_trim_result.messages

        # 2. Prepare Audit Messages (Fast Synchronous Context)
        audit_messages = extraction_messages
        if has_structured_input and len(audit_messages) > 25:
            preserved = audit_messages[:3] + audit_messages[-12:]
            logger.info(f"[AuditService] 📉 Truncated audit context: {len(audit_messages)} → {len(preserved)} msgs (structured input available)")
            audit_messages = preserved

        # Sanitize config: remove callbacks that leak audit to DB/SSE
        clean_config = dict(config or {})
        if "callbacks" in clean_config:
            callbacks = clean_config["callbacks"]
            if isinstance(callbacks, list):
                clean_config["callbacks"] = [
                    cb for cb in callbacks
                    if cb.__class__.__name__ not in ("DatabaseCallbackHandler", "TransparentCallbackHandler")
                ]

        execution_state = state.model_copy(update={"messages": audit_messages})

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

        # Parse outcome from audit messages
        from app.core.engine.message.utils import get_message_text

        audit_messages = result.messages or []
        full_text = "".join(
            get_message_text(m)
            for m in audit_messages
            if _role(m) in ("assistant", "ai")
        )
        outcome_match = re.search(
            r"<evoloop_audit_outcome>(.*?)</evoloop_audit_outcome>",
            full_text,
            re.IGNORECASE | re.DOTALL,
        )
        final_outcome = outcome_match.group(1).strip() if outcome_match else "COMPLETED"
        state.final_outcome = final_outcome

        # Append Finish node tool calls to global tool_history with finish: prefix
        if result.tool_history:
            prefixed = [f"finish:{t}" for t in result.tool_history]
            state.tool_history = (state.tool_history or []) + prefixed

        duration = (time.time() - start) * 1000

        # Background extraction
        await self._dispatch_extraction(
            state=state,
            config=config,
            project_id=project_id,
            summary=summary,
            messages=extraction_messages,
        )

        return AuditResult(
            summary=summary,
            meta={"duration_ms": duration, "outcome": final_outcome},
            messages=result.messages or [],
        )

    async def _dispatch_extraction(
        self,
        state: AgentState,
        config: RunnableConfig,
        project_id: int,
        summary: str,
        messages: list,
    ) -> None:
        from app.core.engine.tasks import engine_audit_structured_extraction
        from app.core.events.base import system_bus
        from app.core.events.schemas.lifecycle import ExtractionRequestedEvent

        thread_id = state.thread_id or config.get("configurable", {}).get("thread_id")
        if not thread_id:
            logger.warning("[AuditService] No thread_id available, skipping background extraction.")
            return

        req_event = ExtractionRequestedEvent(thread_id=thread_id)
        await system_bus.publish(req_event, sequential=True)

        if not req_event.requests:
            logger.info("[AuditService] No extraction schemas requested, skipping background extraction.")
            return

        logger.info(
            f"[AuditService] Dispatched extraction to background worker "
            f"with {len(req_event.requests)} schemas"
        )

        run_id = config.get("configurable", {}).get("run_id")
        member_id_val = config.get("configurable", {}).get("member_id")
        member_id = int(member_id_val) if member_id_val is not None else None

        msg_dicts = [m.model_dump() for m in messages]

        schema_dicts = [req.model_dump() for req in req_event.requests]

        engine_audit_structured_extraction.delay(
            thread_id=thread_id,
            project_id=project_id,
            member_id=member_id,
            run_id=run_id,
            summary=summary,
            messages_dicts=msg_dicts,
            collected_schemas=schema_dicts,
        )
