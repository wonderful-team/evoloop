"""Macro skill execution tool."""

import logging
from typing import Annotated, Any

from sqlalchemy import func, select

from app.core.engine.message.native_classes import RunnableConfig
from app.core.learning.skill_visibility import visible_filter
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill
from app.utils.controller_response import ControllerResponse, SkillResponse

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.run_macro",
)
async def run_macro(
    skill_name: str | None = None,
    skill_id: int | None = None,
    params: dict[str, Any] | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    from app.core.execution.macro.service import MacroService

    thread_id = "default"
    if config:
        cfgable = (
            config.get("configurable", {})
            if isinstance(config, dict)
            else getattr(config, "configurable", {})
        )
        thread_id = cfgable.get("thread_id", "default") or "default"

    skill = None
    try:
        async with session_scope() as db:
            if skill_id is not None:
                skill = await db.get(LearnedSkill, skill_id)
            elif skill_name:
                stmt = select(LearnedSkill).where(
                    func.lower(LearnedSkill.name) == skill_name.lower(),
                    visible_filter(),
                )
                result = await db.execute(stmt)
                skill = result.scalar_one_or_none()
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        return ControllerResponse.error(
            f"Failed to look up skill '{skill_name or skill_id}'",
            details=str(e),
        )

    if not skill:
        identifier = f"id={skill_id}" if skill_id else f"name='{skill_name}'"
        return ControllerResponse.not_found(identifier, item_type="skill")

    from app.core.learning.skill_visibility import is_routable

    if not is_routable(skill):
        return ControllerResponse.error(
            f"Skill '{skill.name}' is not confirmed yet (status: {skill.status}).",
            note="Confirm the skill in the Skill Library before executing it.",
        )

    macro_script = None
    if skill.macro_script:
        from app.utils.yaml import macro_from_yaml
        try:
            macro_script = macro_from_yaml(skill.macro_script)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
            return ControllerResponse.error(
                f"Failed to parse macro YAML for skill '{skill.name}'",
                details=str(e),
            )

    if not macro_script or not isinstance(macro_script, list) or len(macro_script) == 0:
        mode = skill.execution_mode or "agentic"
        return ControllerResponse.error(
            f"Skill '{skill.name}' has no macro script.",
            details=f"Mode: {mode}\nInstructions: {skill.instructions or 'None'}",
            note="This skill requires agentic execution.",
        )

    if skill.execution_mode != "deterministic":
        return ControllerResponse.error(
            f"Skill '{skill.name}' is not in deterministic mode.",
            details=f"Current mode: {skill.execution_mode}\nInstructions: {skill.instructions or 'None'}",
            note="Follow the SOP instructions above instead.",
        )

    logger.info(
        f"[run_macro] Executing skill '{skill.name}' (id={skill.id}) "
        f"with {len(macro_script)} steps, params={params}"
    )

    execution_params = params.copy() if params else {}
    execution_params["_skill_id"] = skill.id
    execution_params["_skill_name"] = skill.name

    result = await MacroService.run(
        thread_id=thread_id,
        script_input=macro_script,
        params=execution_params,
        skill=skill,
    )

    if result.get("success"):
        return SkillResponse.success(skill.name, result.get("extracted_data"))
    else:
        return SkillResponse.error(
            skill.name,
            result.get("message", "Unknown error"),
            fallback_context=result.get("fallback_context"),
            suggestions=result.get("suggestions", []),
        )
