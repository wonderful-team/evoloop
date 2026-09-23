"""Core command execution — synchronous and tool-level interfaces."""

import logging
import shlex
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.execution.constants import (
    MAX_COMMAND_TIMEOUT_SECONDS,
    MIN_COMMAND_TIMEOUT_SECONDS,
    QUICK_TIMEOUT_SECONDS,
)
from app.core.execution.terminal.background.runner import (
    execute_in_background,
    execute_smart,
)
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg

logger = logging.getLogger(__name__)

#: 已知会改写文件的 shell 命令（用于定位 sudo/env 前缀后的真实命令）
_WRITE_COMMANDS = ("rm", "mv", "cp", "sed")


def _parse_command_targets(args: dict) -> list[str]:
    """Extract file paths a shell command may mutate.

    归属执行中心（execute_command 自身的路径声明）。启发式覆盖：
    - ``rm`` / ``mv`` / ``cp``：非 flag 的路径参数（mv/cp 的源与目标都受影响）
    - ``sed -i``：原地修改，取脚本之后的文件参数
    - ``echo`` / ``printf`` 等重定向目标（``>`` / ``>>``，支持多重定向）
    - ``sudo`` / ``env`` 前缀：跳过其 flag/参数，定位到真实命令

    尽力而为：无法可靠解析时返回空列表（最多少一次 diff 快照，不影响执行）。
    """
    command = (args or {}).get("command", "")
    if not isinstance(command, str) or not command.strip():
        return []

    # background 命令在后台异步执行，工具返回时文件可能尚未改完——
    # 此时算 diff 时序不确定（快则落、慢则不落）。明确不进入 diff 追踪，
    # 避免半成品/不完整变更被记录进 changeset。
    if (args or {}).get("background"):
        return []

    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    if not tokens:
        return []

    cmd, rest = _resolve_command(tokens)
    if cmd in ("rm", "mv", "cp"):
        return [t for t in rest[1:] if not t.startswith("-")]

    if cmd == "sed":
        # 仅 -i（原地修改）才影响文件
        if not any(t == "-i" or (t.startswith("-i") and len(t) > 2) for t in rest):
            return []
        non_flag = [t for t in rest[1:] if not t.startswith("-")]
        # 第一个非 flag 是 sed 脚本（或空后缀），其后才是文件
        return non_flag[1:] if non_flag else []

    # 重定向目标（echo / printf 等），收集全部
    targets = []
    for i, t in enumerate(rest):
        if t in (">>", ">") and i + 1 < len(rest):
            targets.append(rest[i + 1])
    return targets


def _resolve_command(tokens: list[str]) -> tuple[str, list[str]]:
    """定位真实命令：剥离 sudo/env 前缀及其 flag/参数。"""
    base = tokens[0].rsplit("/", 1)[-1]
    if base not in ("sudo", "env"):
        return base, tokens

    tail = tokens[1:]
    for i, t in enumerate(tail):
        b = t.rsplit("/", 1)[-1]
        if b in _WRITE_COMMANDS:
            return b, tail[i:]
    # sudo/env 后未找到已知写命令 → 视为非写命令
    return "", []


@evoloop_tool(
    name="bash",
    is_state_mutating=True,
    affected_path_extractor=_parse_command_targets,
    summary_template="evoloop.tool_summary.bash",
)
async def execute_command(
    command: str,
    background: bool = False,
    timeout: int = QUICK_TIMEOUT_SECONDS,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """在用户机器上执行 shell 命令。只用于真实的系统命令 / 终端操作 / 运行脚本。

    **禁止用 bash 做以下事：**
    - 读文件（用 read 工具）、写文件（用 write/edit）、搜索（用 glob/grep）、编辑（用 edit）。
    - 给用户发消息（直接用文本回复，不要用 echo/printf）。

    所有文件路径必须在当前会话工作目录内；不要写 /tmp 或项目路径之外。
    在项目工作目录下运行命令；避免 cd 链，尽量用 workdir。

    Args:
        command: 要执行的命令。
        background: 是否后台执行（长任务）。
        timeout: 超时秒数。
    """
    timeout = min(
        max(timeout, MIN_COMMAND_TIMEOUT_SECONDS), MAX_COMMAND_TIMEOUT_SECONDS
    )

    if background:
        return await execute_in_background(command, timeout, config)
    else:
        return await execute_smart(command, timeout, config)
