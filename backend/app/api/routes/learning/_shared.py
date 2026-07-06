"""
Shared imports and helpers for learning sub-routers.
"""
import json
import logging

from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.execution.macro.service import MacroService
from app.models import (
    LearnedSkill,
)
from app.utils.template import render_template

logger = logging.getLogger(__name__)

#: Active recording sessions (shared across sub-routers)
_active_sessions: dict[str, dict] = {}


def _normalize_skill_params(params_raw: str | list | dict | None) -> list[dict]:
    """Normalize skill parameters from various formats to a standard list."""
    if not params_raw:
        return []

    try:
        if isinstance(params_raw, str):
            data = json.loads(params_raw)
        else:
            data = params_raw
    except (json.JSONDecodeError, TypeError):
        return []

    normalized = []

    if isinstance(data, dict):
        for name, info in data.items():
            if isinstance(info, dict):
                normalized.append({
                    "name": name,
                    "type": info.get("type", "string"),
                    "description": info.get("description", ""),
                    "required": info.get("required", True),
                    "default": info.get("default")
                })
            else:
                normalized.append({
                    "name": name,
                    "type": "string",
                    "description": str(info),
                    "required": True,
                    "default": None
                })
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "name" in item:
                normalized.append({
                    "name": item["name"],
                    "type": item.get("type") or "string",
                    "description": item.get("description", ""),
                    "required": item.get("required", True),
                    "default": item.get("default")
                })

    return normalized


async def execute_macro_with_fallback(
    thread_id: str,
    project_id: int,
    skill: LearnedSkill,
    macro_payload: list,
    params: dict
):
    """Execute a deterministic macro with unified self-healing policy."""
    execution_params = params.copy() if params else {}
    execution_params["_skill_id"] = skill.id
    execution_params["_skill_name"] = skill.name

    result = await MacroService.run(
        thread_id=thread_id,
        script_input=macro_payload,
        params=execution_params,
        skill=skill
    )

    if result.get("status") != "fallback_required":
        return

    if not result.get("allow_self_healing", True):
        logger.warning(
            f"[{thread_id}] Macro failed, but Self-Healing is DISABLED "
            f"(reason: {result.get('healing_disabled_reason', 'unknown')}). Skipping fallback."
        )
        return

    logger.warning(f"[{thread_id}] Macro failed, triggering Agentic Fallback...")
    fallback_ctx = result.get("fallback_context", {})

    fallback_msg = render_template(
        "core/learning/self_healing.prompt.j2",
        skill_name=skill.name,
        failure_context=fallback_ctx,
    )

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=fallback_msg,
        project_id=project_id,
        model=skill.active_model,
        metadata={"goal_prefix": "[Self-Healing] "},
    )

    if result.status == "failed":
        logger.error(f"[MacroFallback] Dispatch failed: {result.error}")
        return

    await run_agent_background(thread_id, result.inputs)
