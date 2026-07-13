"""
Shared imports and helpers for learning sub-routers.
"""
import json
import logging

logger = logging.getLogger(__name__)

#: Active recording sessions (shared across sub-routers)
_active_sessions: dict[str, dict] = {}


def _normalize_json_list(raw: str | list | None) -> list:
    """Normalize a JSON column that may be a list, a JSON string, or a
    double-encoded JSON string (legacy rows store json.dumps inside a JSON
    column, which deserializes back to a str)."""
    if not raw:
        return []
    data = raw
    for _ in range(2):
        if not isinstance(data, str):
            break
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return []
    return data if isinstance(data, list) else []


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
