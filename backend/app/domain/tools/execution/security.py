"""Command security — dangerous pattern detection."""

import logging
import os
import re

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_dangerous_command(command: str) -> tuple[bool, str]:
    cmd_lower = command.lower()

    if re.search(r"rm\s+-r[f\s]*\s+/", cmd_lower):
        return True, "Command contains blocked pattern: destructive rm on root."

    if re.search(r">\s*~/\.bashrc|>\s*~/\.zshrc", cmd_lower):
        return True, "Command contains blocked pattern: modification of shell config."

    if "../.." in cmd_lower:
        return True, "Command contains blocked pattern: deep directory traversal (../../)."

    home_dir = os.path.expanduser("~")
    restricted_dirs = [
        os.path.join(home_dir, "Desktop"),
        os.path.join(home_dir, "Documents"),
        os.path.join(home_dir, "Downloads"),
    ]

    if ">" in command or ">>" in command:
        for restricted in restricted_dirs:
            if restricted in command or restricted.replace(home_dir, "~") in command:
                return True, f"Cannot write to {restricted} using execute_command. Use write_file tool instead."

    if settings.MULTI_TENANT_MODE:
        system_dirs_pattern = r"/(etc|root|var|boot|dev|sys|proc|sbin|lib)(/|$)"
        if re.search(system_dirs_pattern, cmd_lower):
            return True, "Path access blocked: System directories cannot be accessed in Multi-Tenant mode."

    return False, ""


# 命令内显式 cd / pushd 越出工作目录的检测：
# 工具会把命令包装为 "cd {working_dir} && {command}"，命令自身再 cd 到绝对
# 路径（含 ~/xxx）或 cd .. 会覆盖前缀从而逃出沙箱。工作目录是项目根，
# 任何 cd .. / cd ~/绝对路径 都视为越界。
_ESCAPE_CD_RE = re.compile(r"(?<![\w-])(?:cd|pushd)\s+(?:~?/|\.\.(?=/|\s|$))")


def has_workspace_escape(command: str) -> str | None:
    """Return the offending ``cd`` fragment when ``command`` tries to escape the workspace."""
    for match in _ESCAPE_CD_RE.finditer(command):
        return match.group(0)
    return None
