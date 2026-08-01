import logging

from pydantic import Field

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager
from app.core.tools import evoloop_tool
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class SynthesizeSkillInput(DynamicBaseModel):
    reason: str = Field(
        ...,
        description="Reason for triggering skill synthesis. Explain why this session is valuable (e.g., 'Successfully solved a complex bug', 'Implemented a new reusable component')."
    )
    thread_id: str | None = Field(
        None,
        description="The thread ID to synthesize. Defaults to current thread if not provided."
    )


class CreateMacroInput(DynamicBaseModel):
    name: str = Field(
        ...,
        description="A concise, descriptive name for the macro (e.g. '打开腾讯会议并复制链接')."
    )
    description: str = Field(
        ...,
        description="A brief description of what this macro does."
    )
    trigger_patterns: list[str] = Field(
        default_factory=list,
        description="Optional voice/text trigger patterns (e.g. ['快速会议', '创建会议']). If empty, patterns will be auto-generated."
    )
    thread_id: str | None = Field(
        None,
        description="The thread ID to create macro. Defaults to current thread if not provided."
    )


@evoloop_tool(
    args_schema=SynthesizeSkillInput,
    is_state_mutating=False,
    summary_template="evoloop.tool_summary.synthesize_skill"
)
async def synthesize_skill(reason: str, thread_id: str | None = None) -> str:
    """
    Manually trigger skill synthesis for the current or a specific thread.
    Use this when you have successfully completed a non-trivial task that 
    could be useful for future reference or tool creation.
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
                "auto_synthesize": True
            },
        )
        return (
            f"Skill synthesis queued for thread {target_thread}. If the thread "
            f"has enough trace events, a candidate skill will be synthesized in "
            f"the background and saved as pending review — confirm it in the "
            f"Skill Library before it becomes usable."
        )
    except Exception as e:
        logger.error(f"Failed to trigger synthesis tool: {e}")
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
) -> str:
    """
    Persist the current execution trace as a reusable deterministic macro.

    Call this after successfully completing a multi-step desktop/mobile
    automation task. The tool replays the trace, compiles it into a YAML
    macro script, and saves it to the macro library as 'pending_review'.

    The macro will only be created if the trace contains replayable UI
    actions (clicks, taps, inputs, navigations).
    """
    ctx = ContextManager.current()
    target_thread = thread_id or (ctx.thread_id if ctx else None)

    if not target_thread:
        return "Error: Could not determine thread_id for macro creation."

    logger.info(
        "[Tool] Agent triggered macro macro creation for thread %s. name=%r",
        target_thread, name,
    )

    try:
        from app.core.execution.macro.macro_creator_service import (
            MacroCreatorService,
            SynthesisResult,
        )
        from app.core.execution.macro.lifecycle import (
            create_macro_from_synthesis,
        )

        is_eligible = await MacroCreatorService.is_eligible(target_thread)
        if not is_eligible:
            return (
                "This thread does not contain replayable UI actions "
                "(e.g., clicks, taps, inputs). Macro macro creation requires "
                "a trace with at least 2 replayable steps. Please complete "
                "the task first, then try again."
            )

        member_id = ctx.member_id if ctx else 0
        project_id = ctx.project_id if ctx else DEFAULT_PROJECT_ID

        macro = await MacroCreatorService.create_macro_from_trace(
            thread_id=target_thread,
            member_id=member_id,
            name=name,
            description=description,
            trigger_patterns=trigger_patterns,
        )

        if macro is None:
            return (
                "Macro macro creation completed but no macro was created. "
                "The trace may not contain enough actionable steps."
            )

        macro_id = macro.id if hasattr(macro, "id") else macro.get("id")

        return (
            f"✅ Macro created (ID: {macro_id}, name: {name}). "
            f"It is saved as 'pending_review' — please confirm it in the "
            f"Skill Library before it becomes active."
        )
    except Exception as e:
        logger.error(f"Failed to create macro macro: {e}")
        return f"Error: Failed to create_macro macro: {str(e)}"
