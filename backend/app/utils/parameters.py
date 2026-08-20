"""Shared parameter utilities for skills and macros.

Both LearnedSkill and Macro store parameters as a JSON list of dicts with the
same schema. Keeping the normalization, missing-required check, and macro
placeholder derivation in a neutral module lets learning and execution/macro
avoid importing each other.
"""

from __future__ import annotations

import json
import re
from typing import Any

# {{ name }} / {{ a.b }} placeholders consumed by MacroEngine injection.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_]\w*)\s*(?:\.[^}]+)?\}\}")


def derive_parameters_from_macro(macro_script: str | None) -> list[dict[str, Any]]:
    """Derive required string parameters from ``{{ name }}`` placeholders.

    A placeholder left unsubstituted would silently corrupt replay, so every
    derived parameter is required. Returns [] when there is nothing to derive.
    """
    if not macro_script:
        return []
    names = sorted({m.group(1) for m in _PLACEHOLDER_RE.finditer(macro_script)})
    return [{"name": n, "type": "string", "required": True} for n in names]


def normalize_parameters(parameters: Any) -> list[dict[str, Any]]:
    """Coerce SkillParameter objects / dicts / JSON strings into plain dicts."""
    if parameters is None:
        return []
    if isinstance(parameters, str):
        try:
            parameters = json.loads(parameters)
        except (ValueError, TypeError):
            return []
    if not isinstance(parameters, list):
        return []
    out: list[dict[str, Any]] = []
    for p in parameters:
        if hasattr(p, "model_dump"):
            p = p.model_dump()
        elif not isinstance(p, dict) and hasattr(p, "__dict__"):
            p = {k: v for k, v in vars(p).items() if not k.startswith("_")}
        if isinstance(p, dict) and p.get("name"):
            out.append(
                {
                    "name": str(p["name"]),
                    "type": str(p.get("type") or "string"),
                    "description": str(p.get("description") or ""),
                    "required": bool(p.get("required", True)),
                    "default": p.get("default"),
                }
            )
    return out


def finalize_macro_parameters(declared: list[dict] | None, script_yaml: str | None) -> list[dict[str, Any]]:
    """Resolve a macro's parameter declaration for agent-written scripts.

    Explicitly declared parameters win; otherwise derive required string
    parameters from ``{{placeholder}}`` usage in the script. ``{{base_url}}``
    is injected by the engine at runtime and never becomes a macro parameter.
    """
    normalized = normalize_parameters(declared)
    if normalized:
        return normalized
    derived = derive_parameters_from_macro(script_yaml)
    return [p for p in derived if p["name"] != "base_url"]


def missing_required_params(parameters: Any, provided: dict[str, Any] | None) -> list[str]:
    """Names of required parameters absent from the execution request.

    Shared by the REST execute endpoint, the voice executor, and the macro
    runner so a replay script never runs with unsubstituted ``{{ name }}``
    placeholders.
    """
    provided = provided or {}
    try:
        params = json.loads(parameters) if isinstance(parameters, str) else parameters
    except (ValueError, TypeError):
        return []
    if not isinstance(params, list):
        return []
    missing = []
    for p in params:
        if isinstance(p, dict) and p.get("required"):
            name = p.get("name")
            if name and provided.get(name) in (None, ""):
                missing.append(str(name))
    return missing
