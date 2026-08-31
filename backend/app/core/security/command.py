"""Command security — dangerous pattern detection and workspace escape checks.

These rules are used by both the synchronous command execution path and the
background execution path, as well as by the security hook layer.
"""

from __future__ import annotations

import logging
import os
import re

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_dangerous_command(command: str) -> tuple[bool, str]:
    """Return (is_dangerous, reason) for a shell command string."""
    cmd_lower = command.lower()

    if re.search(r"rm\s+-r[f\s]*\s+/", cmd_lower):
        return True, "Command contains blocked pattern: destructive rm on root."

    if re.search(r">\s*~/\.bashrc|>\s*~/\.zshrc", cmd_lower):
        return True, "Command contains blocked pattern: modification of shell config."

    if "../.." in cmd_lower:
        return (
            True,
            "Command contains blocked pattern: deep directory traversal (../../).",
        )

    home_dir = os.path.expanduser("~")
    restricted_dirs = [
        os.path.join(home_dir, "Desktop"),
        os.path.join(home_dir, "Documents"),
        os.path.join(home_dir, "Downloads"),
    ]

    if ">" in command or ">>" in command:
        for restricted in restricted_dirs:
            if restricted in command or restricted.replace(home_dir, "~") in command:
                return (
                    True,
                    f"Cannot write to {restricted} using bash. Use write tool instead.",
                )

    if settings.MULTI_TENANT_MODE:
        system_dirs_pattern = r"/(etc|root|var|boot|dev|sys|proc|sbin|lib)(/|$)"
        if re.search(system_dirs_pattern, cmd_lower):
            return (
                True,
                "Path access blocked: System directories cannot be accessed in Multi-Tenant mode.",
            )

    return False, ""


# 命令内显式 cd / pushd 越出允许目录的检测：
# 工具会把命令包装为 "cd {working_dir} && {command}"，命令自身再 cd
# 到绝对路径（含 ~/xxx）或 cd .. 会覆盖前缀从而逃出沙箱。因此任何 cd
# 目标必须落在 allowed_roots 之一（工作目录、WORKSPACE_ROOT、EvoLoop
# 应用数据目录等）。
_CD_RE = re.compile(r"(?<![\w-])(?:cd|pushd)\s+(\S+)")


def _resolve_cd_target(token: str, base_dir: str | None = None) -> str | None:
    """把 cd 后面的路径 token 解析成绝对路径；无法解析时返回 None。"""
    token = token.strip().strip("'\"`")
    if not token:
        return None
    # 去掉尾部 shell 分隔符（; && || | ）
    token = token.rstrip(";&|")
    if not token or token == "-":
        return None

    expanded = os.path.expandvars(os.path.expanduser(token))
    if os.path.isabs(expanded):
        try:
            return os.path.abspath(expanded)
        except OSError:
            return expanded

    if base_dir:
        try:
            return os.path.abspath(os.path.join(os.path.expanduser(base_dir), expanded))
        except OSError:
            return None

    # 没有 base_dir 时，相对路径无法安全解析
    return None


def _is_under_any_root(path: str, roots: list[str]) -> bool:
    """判断 path 是否等于某个允许根目录或是其下的子目录。"""
    for root in roots:
        if not root:
            continue
        try:
            root_real = os.path.abspath(os.path.expanduser(root))
            path_real = os.path.abspath(os.path.expanduser(path))
            if os.path.commonpath([root_real, path_real]) == root_real:
                return True
        except ValueError:
            continue
    return False


def has_workspace_escape(
    command: str,
    working_dir: str | None = None,
    allowed_roots: list[str] | None = None,
) -> str | None:
    """
    Return the offending ``cd`` fragment when ``command`` tries to escape allowed roots.

    如果提供了 allowed_roots，则只拦截落在允许根目录之外的 cd/pushd；
    否则维持旧行为，拦截所有 cd ~/、cd /、cd ..。
    """
    roots = [r for r in (allowed_roots or []) if r]
    base = working_dir or os.getcwd()

    for match in _CD_RE.finditer(command):
        target = _resolve_cd_target(match.group(1), base_dir=base)
        if target is None:
            # 无法解析的目标（如 cd -）直接拦截
            return match.group(0)

        if roots:
            if _is_under_any_root(target, roots):
                continue
        else:
            # 兼容旧行为：没有 allowed_roots 时，任何 cd 到 ~ / 或 .. 都拦截
            token = match.group(1).strip().strip("'\"`").rstrip(";&|")
            if re.match(r"(~?/|\.\.(?=/|\s|$))", token):
                return match.group(0)
            continue

        return match.group(0)

    return None
