"""
G5 security gate for the two escape-hatch macro step kinds (design doc G5):

1. applescript steps: static review before execution — banned constructs are
   shell escape (`do shell script`), privilege escalation
   (`with administrator privileges`, `sudo`) and nested script runners
   (`osascript`). Pure `tell application` UI automation passes.
2. native steps: default-deny whitelist. Allowed entries come from env
   EVO_NATIVE_STEP_WHITELIST (JSON list):
     [{"command": "python3", "script_prefix": "/abs/path/dir/", "sha256": "..."}]
   command and script_prefix must match; sha256 (of the script file) is
   checked when present ("生成期登记，运行时核对").
"""

from __future__ import annotations

import json
import logging
import os
import re

from app.core.file import compute_file_hash

logger = logging.getLogger(__name__)

# Ordered: most specific first (error messages name the matched rule).
_BANNED_APPLESCRIPT: list[tuple[re.Pattern, str]] = [
    (re.compile(r"do\s+shell\s+script", re.IGNORECASE), "shell 逃逸 do shell script"),
    (re.compile(r"with\s+administrator\s+privileges", re.IGNORECASE), "提权 with administrator privileges"),
    (re.compile(r"\bsudo\b", re.IGNORECASE), "sudo"),
    (re.compile(r"\bosascript\b", re.IGNORECASE), "嵌套 osascript"),
]

_ENV_WHITELIST = "EVO_NATIVE_STEP_WHITELIST"


class ScriptGateError(ValueError):
    """A macro escape-hatch step was rejected by the security gate."""


def review_applescript(script: str) -> None:
    """Raise ScriptGateError on banned AppleScript constructs."""
    for pattern, label in _BANNED_APPLESCRIPT:
        if pattern.search(script):
            raise ScriptGateError(f"AppleScript 静态审查拒绝: {label}")


def _whitelist() -> list[dict]:
    raw = os.environ.get(_ENV_WHITELIST, "").strip()
    if not raw:
        return []
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"[script_gate] {_ENV_WHITELIST} 解析失败，按空白名单处理: {e}")
        return []
    return entries if isinstance(entries, list) else []


def check_native_allowed(command: str, script_path: str) -> None:
    """Default-deny: native steps run only when whitelisted by env config."""
    entries = _whitelist()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("command") and entry["command"] != command:
            continue
        prefix = entry.get("script_prefix")
        if prefix and not script_path.startswith(prefix):
            continue
        expected_hash = entry.get("sha256")
        if expected_hash:
            try:
                actual = compute_file_hash(script_path, algo="sha256")
            except OSError as e:
                raise ScriptGateError(f"native 步骤脚本不可读: {script_path} ({e})") from e
            if actual != expected_hash:
                raise ScriptGateError(f"native 步骤脚本 hash 不匹配: {script_path}")
        return
    raise ScriptGateError(
        f"native 步骤未在白名单（{_ENV_WHITELIST}）: {command} {script_path}"
    )
