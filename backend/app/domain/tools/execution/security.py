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
