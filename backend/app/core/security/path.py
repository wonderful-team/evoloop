"""Centralized path safety helpers for tools and hooks.

This module provides a single source of truth for "which paths an Agent tool is
allowed to touch". The allowed roots are:

- the current thread/project working directory
- ``WORKSPACE_ROOT``
- the EvoLoop app data directory (``~/.evoloop``)
- any prefix configured in ``settings.ALLOWED_PATH_PREFIXES``

Anything under ``~/.evoloop`` is treated as safe application data. Only
``.evoloop`` directories that live inside a project workspace are considered
project metadata and remain protected.
"""

from __future__ import annotations

import os
import re

from app.core.config import settings
from app.core.project.utils import get_workspace_root


def _normalize_path(path: str) -> str:
    """Return a clean absolute path, expanding ``~`` and resolving symlinks."""
    try:
        return os.path.realpath(os.path.expanduser(path))
    except OSError:
        return os.path.abspath(os.path.expanduser(path))


def get_allowed_roots(
    working_dir: str | None = None,
    project_path: str | None = None,
    member_id: int | None = None,
) -> list[str]:
    """Build the list of directories tools are allowed to access.

    Only directories that actually exist on disk are returned, so callers don't
    accidentally whitelist a non-existent path.

    多租户（MULTI_TENANT_MODE=true）下按用户隔离：
    - 工作根只允许 ``workspace/<member_id>``（A 用户看不到 B 的目录）；
    - 不再放行全局 WORKSPACE_ROOT / 全局 APP_DATA_DIR / ALLOWED_PATH_PREFIXES
      （宿主运维白名单是单用户运维模式语义，多租户下成员一律不具宿主权限）；
    - 覆盖面：member 根、member 上传目录、（指定/解析出的）project path。
    调用方传递 member_id 时优先，否则从执行上下文兜底；未知 member → 仅
    project path 与 working_dir 白名单有效（保守降级，禁全局根）。
    """
    from app.core.config import settings as _settings
    from app.core.project.utils import (
        current_member_id,
        resolve_member_workspace_root,
    )

    multi_tenant = _settings.MULTI_TENANT_MODE
    roots: set[str] = set()

    if working_dir and working_dir != ".":
        roots.add(_normalize_path(working_dir))

    if project_path:
        roots.add(_normalize_path(project_path))

    if not multi_tenant:
        roots.add(_normalize_path(settings.APP_DATA_DIR))

        workspace_root = get_workspace_root()
        if workspace_root:
            roots.add(_normalize_path(workspace_root))

        for prefix in settings.ALLOWED_PATH_PREFIXES:
            roots.add(_normalize_path(prefix))
    else:
        member = member_id if member_id else current_member_id()
        member_root = resolve_member_workspace_root(member) if member else ""
        if member_root:
            roots.add(_normalize_path(member_root))
            # member 级上传目录（不存在则不加，返回值只含真实目录）
            upload_dir = os.path.join(member_root, "uploads")
            if os.path.isdir(upload_dir):
                roots.add(_normalize_path(upload_dir))

    return sorted(r for r in roots if os.path.isdir(r))


def is_under_allowed_root(
    path: str,
    *,
    allowed_roots: list[str] | None = None,
    working_dir: str | None = None,
) -> bool:
    """Return ``True`` if ``path`` lies within one of the allowed roots."""
    roots = (
        allowed_roots if allowed_roots is not None else get_allowed_roots(working_dir)
    )
    if not roots:
        return False

    resolved = _normalize_path(path)
    for root in roots:
        if resolved == root or resolved.startswith(root + os.sep):
            return True
    return False


def is_path_safe(
    path: str,
    *,
    working_dir: str | None = None,
    project_path: str | None = None,
    allowed_roots: list[str] | None = None,
) -> bool:
    """Check whether ``path`` is safe to access.

    Relative paths are resolved against ``working_dir`` first, matching the
    behavior of file tools and the authorization gate.
    """
    if not path:
        return False

    if working_dir and not os.path.isabs(path):
        candidate = os.path.join(_normalize_path(working_dir), os.path.expanduser(path))
    else:
        candidate = os.path.expanduser(path)

    roots = allowed_roots
    if roots is None:
        roots = get_allowed_roots(working_dir=working_dir, project_path=project_path)

    return is_under_allowed_root(candidate, allowed_roots=roots)


def is_project_metadata_path(path: str) -> bool:
    """Return ``True`` if ``path`` points to project-local metadata (``.evoloop``).

    The global app data directory ``~/.evoloop`` is explicitly **not** project
    metadata and returns ``False``.
    """
    if ".evoloop" not in path.lower():
        return False

    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        # A relative ``.evoloop`` reference is assumed to be inside the current
        # project/workspace and therefore protected.
        return True

    resolved = _normalize_path(expanded)
    app_data = _normalize_path(settings.APP_DATA_DIR)
    if resolved == app_data or resolved.startswith(app_data + os.sep):
        return False

    return True


def command_touches_project_metadata(command: str) -> bool:
    """Return ``True`` if shell ``command`` text references project-local metadata.

    ``execute_command`` carries paths as free-form text rather than structured
    fields, so tokens containing ``.evoloop`` are extracted (case-insensitive),
    shell metacharacters are stripped, and only path-like tokens are sent to
    :func:`is_project_metadata_path` for a verdict. The global app data directory
    ``~/.evoloop`` stays exempt via the shared predicate.
    """
    if not command or ".evoloop" not in command.lower():
        return False

    for token in re.findall(r"(?i)\S*\.evoloop\S*", command):
        cleaned = token.strip("'\"\\`;|&()[]{}<>$ \t\n")
        if _is_path_like_token(cleaned) and is_project_metadata_path(cleaned):
            return True
    return False


def _is_path_like_token(token: str) -> bool:
    """Return ``True`` if ``token`` looks like a filesystem path reference.

    避免把 ``echo foo.evoloop.bar`` 这类只是含 ``.evoloop`` 子串的普通词误判为路径。
    """
    if not token:
        return False
    if token.startswith(("/", "./", "../", "~/", "\\")):
        return True
    if "/" in token or "\\" in token:
        return True
    if token.startswith("."):
        return token.startswith(".evoloop") or token.startswith("..")
    return False
