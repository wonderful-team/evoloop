"""
Shared imports and helpers for learning sub-routers.
"""

import json
import logging
from typing import Any

from app.core.learning.schemas import SkillParameter

logger = logging.getLogger(__name__)

#: Active recording sessions (shared across sub-routers)
_active_sessions: dict[str, dict] = {}


def _member_id(current_user: Any) -> int:
    """Safely extract member_id from optional current user."""
    if current_user is None:
        return 0
    return int(current_user.id)


def _normalize_skill_params(params_raw: str | list | dict | None) -> list[SkillParameter]:
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

    normalized: list[SkillParameter] = []

    if isinstance(data, dict):
        for name, info in data.items():
            if isinstance(info, dict):
                normalized.append(
                    SkillParameter(
                        name=name,
                        type=info.get("type", "string"),
                        description=info.get("description", ""),
                        required=info.get("required", True),
                        default=info.get("default"),
                    )
                )
            else:
                normalized.append(
                    SkillParameter(
                        name=name,
                        type="string",
                        description=str(info),
                        required=True,
                    )
                )
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "name" in item:
                normalized.append(
                    SkillParameter(
                        name=item["name"],
                        type=item.get("type") or "string",
                        description=item.get("description", ""),
                        required=item.get("required", True),
                        default=item.get("default"),
                    )
                )

    return normalized
