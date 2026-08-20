import logging
from typing import Any

from pydantic import Field

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager
from app.core.execution.macro import (
    MacroCreatorService,
)
from app.core.execution.macro.lifecycle import (
    confirm_macro,
    create_macro_from_synthesis,
    find_macro_by_name,
)
from app.core.execution.macro.schemas import (
    RISK_TIER_ORDER,
    MacroScript,
    action_family,
    action_risk,
)
from app.core.execution.macro.utils import cleanup_macro_steps, verify_macro_script
from app.core.tools import evoloop_tool
from app.infrastructure.database import session_scope
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.parameters import finalize_macro_parameters

logger = logging.getLogger(__name__)


class SynthesizeSkillInput(DynamicBaseModel):
    reason: str = Field(
        ...,
        description="Reason for triggering skill synthesis. Explain why this session is valuable (e.g., 'Successfully solved a complex bug', 'Implemented a new reusable component').",
    )
    thread_id: str | None = Field(
        None,
        description="The thread ID to synthesize. Defaults to current thread if not provided.",
    )


class CreateMacroInput(DynamicBaseModel):
    name: str = Field(
        ...,
        description="A concise, descriptive name for the macro (e.g. '打开腾讯会议并复制链接').",
    )
    description: str = Field(
        ...,
        description="A brief description of what this macro does."
    )
    trigger_patterns: list[str] = Field(
        default_factory=list,
        description="Optional voice/text trigger patterns (e.g. ['快速会议', '创建会议']). If empty, patterns will be auto-generated.",
    )
    thread_id: str | None = Field(
        None,
        description="The thread ID to create macro. Defaults to current thread if not provided.",
    )
    script_steps: list[dict[str, Any]] | None = Field(
        None,
        description="Optional explicit macro steps. When provided, the macro is built from these steps (Agent-written mode). When omitted, the macro is compiled from the current execution trace.",
    )
    rationale: str | None = Field(
        None,
        description="Required when script_steps is provided. Explain why this macro should be created and how it satisfies the eligibility rules.",
    )


@evoloop_tool(
    args_schema=SynthesizeSkillInput,
    is_state_mutating=False,
    summary_template="evoloop.tool_summary.create_skill_from_session",
)
async def create_skill_from_session(reason: str, thread_id: str | None = None) -> str:
    """
    Create a reusable skill from the current session's activity.

    After completing a valuable task, call this to distill the session's trace
    into a candidate skill in the background. The skill is saved as pending
    review — confirm it in the Skill Library before it becomes usable.
    """
    ctx = ContextManager.current()
    target_thread = thread_id or (ctx.thread_id if ctx else None)
    project_id = ctx.project_id if ctx else DEFAULT_PROJECT_ID

    if not target_thread:
        return "Error: Could not determine thread_id for synthesis."

    logger.info(f"[Tool] Agent triggered manual skill synthesis for thread {target_thread}. Reason: {reason}")

    try:
        from app.infrastructure.queue.factory import get_scheduler

        # Trigger the recording task with auto_synthesize=True.
        # No explicit queue: the Celery worker only consumes the default
        # ("celery") queue, so an explicit queue="default" would silently
        # strand the task in full mode.
        get_scheduler().send_task(
            "engine_record_episode",
            kwargs={
                "thread_id": target_thread,
                "project_id": project_id,
                "auto_synthesize": True,
            },
        )
        return (
            f"Skill synthesis queued for thread {target_thread}. If the thread "
            f"has enough trace events, a candidate skill will be synthesized in "
            f"the background and saved as pending review — confirm it in the "
            f"Skill Library before it becomes usable."
        )
    except Exception as e:
        logger.exception(f"Failed to trigger synthesis tool: {e}")
        return f"Error: Failed to dispatch synthesis task: {str(e)}"


@evoloop_tool(
    args_schema=CreateMacroInput,
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.create_macro",
)
async def create_macro(
    name: str,
    description: str,
    trigger_patterns: list[str] | None = None,
    thread_id: str | None = None,
    script_steps: list[dict[str, Any]] | None = None,
    rationale: str | None = None,
) -> str:
    """
    Persist a reusable deterministic macro.

    Two modes:
    1. Trace mode (script_steps omitted): after completing a multi-step
       desktop/mobile automation task, the tool replays the trace and compiles
       it into a YAML macro script saved as 'pending_review'.
    2. Script mode (script_steps provided): the tool takes an explicit list of
       MacroStep dicts, validates and gates them, then saves the macro as
       'pending_review'. A rationale is required in this mode.

    In script mode, escape-risk steps (bash, native, applescript, run_js) are
    rejected before any dry-run execution because macro verification actually
    executes the script.

    ## MacroStep format for script_steps
    Each step is a dict. Required/common fields:

    - type: "action" | "extract" | "control" | "dump" | "if" | "loop" | "native" | "bash"
    - event_type: depends on type, e.g. "click", "input", "wait", "navigate",
      "open_app", "get_text", "run_js", "applescript", "bash"
    - payload: action-specific data (see examples below)
    - step_number: 1, 2, 3, ...
    - description: optional human-readable note

    Common examples:
      Open an app:
        {"type": "action", "event_type": "open_app", "payload": {"app_name": "WeChat"}, "step_number": 1}
      Click an element:
        {"type": "action", "event_type": "click", "payload": {"selector": {"type": "ax", "value": "发送"}}, "step_number": 2}
      Type into an input:
        {"type": "action", "event_type": "input", "payload": {"selector": {"type": "ax", "value": "搜索框"}, "value": "hello"}, "step_number": 3}
      Wait briefly:
        {"type": "action", "event_type": "wait", "payload": {"seconds": 1}, "step_number": 4}
      Navigate to a URL:
        {"type": "action", "event_type": "navigate", "payload": {"url": "https://example.com"}, "step_number": 5}
      Extract text:
        {"type": "extract", "event_type": "get_text", "extract_type": "get_text", "payload": {"key": "result"}, "step_number": 6}

    Control flow:
      If branch:
        {"type": "if", "condition": {"op": "exists", "selector": {"type": "ax", "value": "确定"}},
         "then_steps": [...], "else_steps": [...], "step_number": 7}
      Loop:
        {"type": "loop", "condition": {"op": "exists", "selector": {"type": "ax", "value": "加载更多"}},
         "steps": [...], "max_iterations": 5, "step_number": 8}

    IMPORTANT: Do NOT include bash, native (applescript/run_js), or any
    escape-risk steps. They will be rejected by the risk gate.
    """
    ctx = ContextManager.current()
    target_thread = thread_id or (ctx.thread_id if ctx else None)
    project_id = ctx.project_id if ctx else DEFAULT_PROJECT_ID
    member_id = ctx.member_id if ctx else 0

    if not target_thread:
        return "Error: Could not determine thread_id for macro creation."

    if script_steps is not None and not rationale:
        return (
            "Error: When providing script_steps, rationale is required. "
            "Explain why this macro should be created."
        )

    logger.info(
        "[Tool] Agent triggered macro creation for thread %s. name=%r script_mode=%s",
        target_thread,
        name,
        script_steps is not None,
    )

    if script_steps is None:
        return await _create_macro_from_trace(
            target_thread, name, description, trigger_patterns, member_id
        )

    return await _create_macro_from_script(
        target_thread=target_thread,
        project_id=project_id,
        member_id=member_id,
        name=name,
        description=description,
        trigger_patterns=trigger_patterns,
        script_steps=script_steps,
        rationale=rationale,
    )


async def _create_macro_from_trace(
    target_thread: str,
    name: str,
    description: str,
    trigger_patterns: list[str] | None,
    member_id: int,
) -> str:
    """Original trace-to-macro path."""
    try:
        is_eligible = await MacroCreatorService.is_eligible(target_thread)
        if not is_eligible:
            return (
                "This thread does not contain replayable UI actions "
                "(e.g., clicks, taps, inputs). Macro creation requires "
                "a trace with at least 2 replayable steps. Please complete "
                "the task first, then try again."
            )

        macro = await MacroCreatorService.create_macro_from_trace(
            thread_id=target_thread,
            member_id=member_id,
            name=name,
            description=description,
            trigger_patterns=trigger_patterns,
        )

        if macro is None:
            return (
                "Macro creation completed but no macro was created. "
                "The trace may not contain enough actionable steps."
            )

        macro_id = macro.id if hasattr(macro, "id") else macro.get("id")

        return (
            f"✅ Macro created (ID: {macro_id}, name: {name}). "
            f"It is saved as 'pending_review' — please confirm it in the "
            f"Skill Library before it becomes active."
        )
    except Exception as e:
        logger.exception(f"Failed to create macro from trace: {e}")
        return f"Error: Failed to create macro from trace: {str(e)}"


async def _create_macro_from_script(
    target_thread: str,
    project_id: int,
    member_id: int,
    name: str,
    description: str,
    trigger_patterns: list[str] | None,
    script_steps: list[dict[str, Any]],
    rationale: str | None,
) -> str:
    """Agent-written macro path: validate, gate, dry-run, persist."""
    try:
        cleaned_steps, _ = cleanup_macro_steps(script_steps)

        try:
            script = MacroScript(steps=cleaned_steps)
        except Exception as e:
            return f"Error: Invalid macro script: {e}"

        allowed_families = {"observe", "act", "control", "data"}
        reason = _scan_step_families(script.steps, allowed_families)
        if reason:
            return f"Error: Risk gate rejected: {reason}"

        result = await verify_macro_script(
            cleaned_steps, thread_id=target_thread, _project_id=project_id
        )
        if not result.success:
            return f"Error: Macro verification failed: {result.error or result.status}"

        max_risk = _compute_max_risk(script.steps)
        requires_confirmation = max_risk in {"money", "escape"}

        async with session_scope() as db:
            existing = await find_macro_by_name(name, project_id=project_id, db=db)
            if existing is not None:
                return f"Error: A macro named '{name}' already exists (id={existing.id})."

            macro = await create_macro_from_synthesis(
                db,
                name=name,
                description=description,
                trigger_patterns=trigger_patterns or [],
                parameters=[],
                macro_script=script.to_yaml(),
                risk_tier=max_risk,
                requires_confirmation=requires_confirmation,
                source_thread_id=target_thread,
                project_id=project_id,
                member_id=member_id,
            )
            macro_id = macro.id

        logger.info(
            "[Tool] Agent-written macro created: id=%s name=%s risk=%s "
            "requires_confirmation=%s rationale=%r",
            macro_id,
            name,
            max_risk,
            requires_confirmation,
            rationale,
        )

        return (
            f"✅ Macro created from script (ID: {macro_id}, name: {name}). "
            f"It is saved as 'pending_review' — confirm it before it becomes active."
        )
    except Exception as e:
        logger.exception(f"Failed to create macro from script: {e}")
        return f"Error: Failed to create macro from script: {str(e)}"


def _scan_step_families(steps: list[Any], allowed: set[str]) -> str | None:
    """Reject any step whose action family is not in the allowed set."""
    for step in steps:
        family = action_family(step.type, step.event_type)
        if family not in allowed:
            return (
                f"step type={step.type} event_type={step.event_type} "
                f"is in disallowed family '{family}'"
            )
        for nested in (step.then_steps, step.else_steps, step.steps):
            if nested:
                reason = _scan_step_families(nested, allowed)
                if reason:
                    return reason
    return None


def _compute_max_risk(steps: list[Any]) -> str:
    """Return the highest risk tier present in the script."""
    max_risk = "observe"
    for step in steps:
        risk = action_risk(step.event_type)
        if RISK_TIER_ORDER.get(risk, 0) > RISK_TIER_ORDER.get(max_risk, 0):
            max_risk = risk
        for nested in (step.then_steps, step.else_steps, step.steps):
            if nested:
                nested_risk = _compute_max_risk(nested)
                if RISK_TIER_ORDER.get(nested_risk, 0) > RISK_TIER_ORDER.get(
                    max_risk, 0
                ):
                    max_risk = nested_risk
    return max_risk
