"""Macro execution tool — replays a deterministic macro from the macros table.

Compat period: legacy skill_id/skill_name lookups fall back to deterministic
learned_skills rows (deprecated, logged) until migration completes.
"""

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


def _resolve_thread_id(config) -> str:
    if not config:
        return "default"
    cfgable = (
        config.get("configurable", {})
        if isinstance(config, dict)
        else getattr(config, "configurable", {})
    )
    return cfgable.get("thread_id", "default") or "default"


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.run_macro",
)
async def run_macro(
    macro_id: int | None = None,
    macro_name: str | None = None,
    skill_id: int | None = None,
    skill_name: str | None = None,
    params: dict[str, Any] | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    from app.core.execution.macro.service import MacroService

    thread_id = _resolve_thread_id(config)

    if macro_id is not None or macro_name is not None:
        return await _run_macro_row(
            macro_id, macro_name, params, thread_id, MacroService
        )

    if skill_id is not None or skill_name is not None:
        logger.info(
            "[run_macro] legacy skill lookup path (deprecated): id=%s name=%s",
            skill_id,
            skill_name,
        )
        return await _run_legacy_skill(
            skill_id, skill_name, params, thread_id, MacroService
        )

    return ControllerResponse.error(
        "run_macro requires macro_id or macro_name",
        note="Use list_macros to discover available macros.",
    )


async def _run_macro_row(macro_id, macro_name, params, thread_id, macro_service) -> str:
    from app.core.execution.macro import lifecycle

    macro = None
    try:
        if macro_id is not None:
            macro = await lifecycle.load_macro(int(macro_id))
        elif macro_name:
            macro = await lifecycle.find_macro_by_name(macro_name)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        return ControllerResponse.error(
            f"Failed to look up macro '{macro_name or macro_id}'",
            details=str(e),
        )

    if macro is None:
        identifier = f"id={macro_id}" if macro_id else f"name='{macro_name}'"
        return ControllerResponse.not_found(identifier, item_type="macro")

    if not macro.is_routable():
        return ControllerResponse.error(
            f"Macro '{macro.name}' is not confirmed yet (status: {macro.status}).",
            note="Confirm the macro in the Macro Library before executing it.",
        )

    from app.utils.yaml import macro_from_yaml

    try:
        steps = macro_from_yaml(macro.macro_script)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        return ControllerResponse.error(
            f"Failed to parse macro YAML for '{macro.name}'",
            details=str(e),
        )

    if not steps:
        return ControllerResponse.error(f"Macro '{macro.name}' has an empty script.")

    logger.info(
        "[run_macro] Executing macro '%s' (id=%s) with %d steps, params=%s",
        macro.name,
        macro.id,
        len(steps),
        params,
    )

    execution_params = params.copy() if params else {}
    execution_params["_macro_id"] = macro.id
    execution_params["_macro_name"] = macro.name

    # Inject project url as base_url for {{base_url}} substitutions
    if "base_url" not in execution_params:
        try:
            from app.core.project.utils import get_project_path, read_project_json
            proj_path = await get_project_path(macro.project_id)
            if proj_path:
                pj = read_project_json(proj_path)
                project_url = pj.get("url")
                if project_url:
                    execution_params["base_url"] = project_url
        except Exception:
            pass

    result = await macro_service.run(
        thread_id=thread_id,
        script_input=steps,
        params=execution_params,
        macro=macro,
    )

    if result.get("success"):
        return SkillResponse.success(macro.name, result.get("extracted_data"))
    return SkillResponse.error(
        macro.name,
        result.get("message", "Unknown error"),
        fallback_context=result.get("fallback_context"),
        suggestions=result.get("suggestions", []),
    )


async def _run_legacy_skill(
    skill_id, skill_name, params, thread_id, macro_service
) -> str:
    from app.models.macro import Macro

    skill = None
    macro = None
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
            if skill is not None and skill.macro_id:
                macro = await db.get(Macro, skill.macro_id)
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

    if macro is None:
        return ControllerResponse.error(
            f"Skill '{skill.name}' has no macro script.",
            note="This skill requires agentic execution.",
        )

    if not macro.is_routable():
        return ControllerResponse.error(
            f"Macro linked to skill '{skill.name}' is not confirmed yet.",
            note="Confirm the macro in the Macro Library before executing it.",
        )

    from app.utils.yaml import macro_from_yaml

    try:
        macro_script = macro_from_yaml(macro.macro_script)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        return ControllerResponse.error(
            f"Failed to parse macro YAML for skill '{skill.name}'",
            details=str(e),
        )

    if not macro_script or not isinstance(macro_script, list) or len(macro_script) == 0:
        return ControllerResponse.error(
            f"Skill '{skill.name}' has no macro script.",
            note="This skill requires agentic execution.",
        )

    execution_params = params.copy() if params else {}
    execution_params["_skill_id"] = skill.id
    execution_params["_skill_name"] = skill.name

    result = await macro_service.run(
        thread_id=thread_id,
        script_input=macro_script,
        params=execution_params,
        macro=macro,
    )

    if result.get("success"):
        return SkillResponse.success(skill.name, result.get("extracted_data"))
    return SkillResponse.error(
        skill.name,
        result.get("message", "Unknown error"),
        fallback_context=result.get("fallback_context"),
        suggestions=result.get("suggestions", []),
    )
