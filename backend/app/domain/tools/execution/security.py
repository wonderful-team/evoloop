"""Backward-compatibility re-export of command security helpers.

The canonical implementation now lives in ``app.core.security.command``.
New code should import from there.
"""

from app.core.security.command import (
    _CD_RE,
    _is_under_any_root,
    _resolve_cd_target,
    has_workspace_escape,
    is_dangerous_command,
)

__all__ = [
    "_CD_RE",
    "_is_under_any_root",
    "_resolve_cd_target",
    "has_workspace_escape",
    "is_dangerous_command",
]
