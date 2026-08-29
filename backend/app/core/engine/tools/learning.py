import logging
from typing import Any

from pydantic import Field

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager
from app.core.learning.macro import MacroCreatorService
from app.core.learning.macro.lifecycle import (
    confirm_macro,
    create_macro_from_synthesis,
    find_macro_by_name,
)
from app.core.learning.macro.schemas import MacroScript
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
        ..., description="A brief description of what this macro does."
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

    logger.info(
        f"[Tool] Agent triggered manual skill synthesis for thread {target_thread}. Reason: {reason}"
    )

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
    parameters: list[dict] | None = None,
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

    In script mode, escape-risk steps (bash, native, applescript, run_js as an
    ACTION step) are rejected before any dry-run execution because macro
    verification actually executes the script.

    ## Evoloop macro authoring standard (MUST follow)

    These are the authoritative conventions used by every verified macro in
    the library. Deviating from them fails dry-run verification:

    1. **Navigate URLs must be absolute and use the `{{base_url}}` placeholder.**
       Never use a relative path: `/shop.html#url=...` fails with
       "Cannot navigate to invalid URL". Always write:
       `{"type": "action", "event_type": "navigate", "payload": {"url": "{{base_url}}/shop.html#url=shop/goods/lists"}}`
       The engine resolves `{{base_url}}` to the project's deployment URL.

    2. **Placeholders only support plain variables.**
       `{{param}}` or `{{parameters.param}}` are injected verbatim. Jinja
       filters/expressions (e.g. `{{ x|default("0") }}`) are NOT supported and
       will remain unresolved. Apply defaults inside JS instead:
       `const v = ('{{order_status}}' === '') ? '0' : '{{order_status}}';`

    3. **run_js is allowed ONLY inside EXTRACT steps** (reading page state).
       run_js as an ACTION step is rejected by the risk gate. JS must be a
       function: `() => {...}` returning a JSON-serializable value.

    4. **Loop/if conditions use this exact schema:**
       `{"type": "loop", "condition": {"type": "element_exists" | "element_visible" | "text_contains", "target_selector": ".css-selector"}, "steps": [...], "max_iterations": 5}`
       Supported condition types: `element_exists`, `element_visible`,
       `text_contains`.

    5. **step_number is auto-normalized** by the engine; duplicates and gaps
       are fixed automatically. You may still number steps for readability.

    6. **Parameterize thresholds** via `parameters` + `{{param}}` placeholders
       instead of hardcoding business values (e.g. stock > 100), so the macro
       can be reused with different inputs. Declare parameters in the
       `parameters` argument as a list of dicts, e.g.
       `[{"name": "stock_threshold", "type": "string", "required": True, "description": "库存阈值"}]`,
       then reference them inside steps as `{{stock_threshold}}`.
       If you omit `parameters`, they are derived automatically from any
       `{{placeholder}}` used in script_steps (each becomes a required string
       parameter). `{{base_url}}` is resolved by the engine and never counts
       as a macro parameter.

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
        {"type": "action", "event_type": "click", "payload": {"selector": {"type": "css", "value": ".btn-confirm"}}, "step_number": 2}
      Type into an input:
        {"type": "action", "event_type": "input", "payload": {"selector": {"type": "css", "value": "#search-input"}, "value": "{{keyword}}"}, "step_number": 3}
      Wait briefly:
        {"type": "action", "event_type": "wait", "payload": {"seconds": 1}, "step_number": 4}
      Navigate to a backend page (correct):
        {"type": "action", "event_type": "navigate", "payload": {"url": "{{base_url}}/shop.html#url=shop/goods/lists"}, "step_number": 5}
      Extract text:
        {"type": "extract", "event_type": "get_text", "extract_type": "get_text", "payload": {"key": "result"}, "step_number": 6}

      Extract structured data via page JavaScript (EXTRACT only):
        {"type": "extract", "event_type": "run_js", "extract_type": "run_js", "key": "orders", "payload": {"script": "() => JSON.stringify({count: document.querySelectorAll('.row').length})"}, "step_number": 7}

    Control flow:
      If branch:
        {"type": "if", "condition": {"type": "element_exists", "target_selector": ".modal-confirm"},
         "then_steps": [...], "else_steps": [...], "step_number": 8}
      Loop:
        {"type": "loop", "condition": {"type": "element_exists", "target_selector": ".layui-laypage-next:not(.layui-disabled)"},
         "steps": [...], "max_iterations": 5, "step_number": 9}

    IMPORTANT: Do NOT include bash, native, or applescript steps. They will be
    rejected by the risk gate. run_js is allowed ONLY inside EXTRACT steps for
    reading page state; run_js as an ACTION step is not allowed.
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
        parameters=parameters,
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

        # No human review step exists for agent-authored macros: the trace
        # itself (a completed, successful real execution) is the verification.
        # Promote so the macro is discoverable.
        async with session_scope() as db:
            confirmed = await confirm_macro(int(macro_id), db=db)

        status_note = (
            "Dry-run verification passed; the macro is active and discoverable via list_macros."
            if confirmed
            else "Activation failed; the macro remains inactive — report this to the user."
        )
        return (
            f"✅ Macro created from trace (ID: {macro_id}, name: {name}). {status_note}"
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
    parameters: list[dict] | None = None,
    rationale: str | None = None,
) -> str:
    """Agent-written macro path: validate, gate, dry-run, persist."""
    try:
        from app.core.learning.macro.authoring import validate_script

        validation = await validate_script(
            script_steps, thread_id=target_thread, project_id=project_id
        )
        if not validation.ok:
            return f"Error: {validation.error}"

        max_risk = validation.max_risk
        requires_confirmation = validation.requires_confirmation

        final_params = finalize_macro_parameters(
            parameters, MacroScript(steps=validation.cleaned_steps).to_yaml()
        )

        async with session_scope() as db:
            existing = await find_macro_by_name(name, project_id=project_id, db=db)
            if existing is not None:
                return (
                    f"Error: A macro named '{name}' already exists (id={existing.id})."
                )

            macro = await create_macro_from_synthesis(
                db,
                name=name,
                description=description,
                trigger_patterns=trigger_patterns or [],
                parameters=final_params,
                macro_script=MacroScript(steps=validation.cleaned_steps).to_yaml(),
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

        # No human review step exists for agent-authored macros: the dry-run
        # verification above IS the gate. Self-verify by promoting to
        # verified/active so the macro is immediately discoverable via
        # list_macros (which only shows verified macros).
        async with session_scope() as db:
            confirmed = await confirm_macro(macro_id, db=db)

        if not confirmed:
            logger.warning(
                "[Tool] Agent-written macro %s failed self-activation; "
                "it remains inactive.",
                macro_id,
            )
            return (
                f"⚠️ Macro created (ID: {macro_id}, name: {name}) and dry-run "
                f"verified, but activation failed. Report the macro ID to the "
                f"user; it is not discoverable yet."
            )

        return (
            f"✅ Macro created and self-verified (ID: {macro_id}, name: {name}, "
            f"risk={max_risk}). Dry-run verification passed and the macro is "
            f"now active and discoverable via list_macros."
        )
    except Exception as e:
        logger.exception(f"Failed to create macro from script: {e}")
        return f"Error: Failed to create macro from script: {str(e)}"
