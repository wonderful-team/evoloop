"""Subagent type registry — single source of truth for each subagent type.

对齐 OpenCode ``agent.ts`` ``Agent.Info``：每个子代理类型由 人格 prompt + 工具面
(tool face) 决定。工具面即权限边界（deny-by-omission，visibleTools 语义）——
不在工具面内的工具对子代理不可见，天然隔离只读类型（explore/reviewer）与
可写类型（general）。
"""

from __future__ import annotations

from dataclasses import dataclass

#: react 主 Agent 全量工具面（agent_main.yaml agents.react.tools）
REACT_FULL_TOOLS = [
    "bash",
    "read",
    "glob",
    "grep",
    "edit",
    "write",
    "task",
    "webfetch",
    "websearch",
    "plan",
    "skill",
    "question",
    "macro",
    "remember",
]

#: 只读工具子集（对齐 OpenCode explore：read/grep/glob/list/bash/webfetch/websearch）
READONLY_TOOLS = [
    "read",
    "glob",
    "grep",
    "bash",
    "webfetch",
    "websearch",
]


@dataclass(frozen=True)
class SubagentType:
    """单个子代理类型定义（OpenCode ``Agent.Info`` 等价物）。"""

    name: str
    prompt: str
    tools: tuple[str, ...]
    description: str
    readonly: bool = False
    #: 是否允许再派生子代理（嵌套 task）。非只读较重类型默认拒绝（对齐 OpenCode
    #: 默认 deny task + subagent_depth=1）。
    allow_nested_task: bool = False


_READONLY_PROMOTE = dict.fromkeys(READONLY_TOOLS)


def _face(*tools: str, read_only: bool = False) -> tuple[str, ...]:
    """构造子代理工具面；read_only 时仅保留只读子集，剔除一切写工具与 task/skill。"""
    if read_only:
        return tuple(t for t in tools if t in _READONLY_PROMOTE)
    return tuple(tools)


SUBTYPES: dict[str, SubagentType] = {
    "explore": SubagentType(
        name="explore",
        prompt="core/agent/subagent.explore.txt",
        tools=_face(
            "read", "glob", "grep", "bash", "webfetch", "websearch", read_only=True
        ),
        description="文件搜索专科，只读工具，快速定位代码/文件",
        readonly=True,
        allow_nested_task=False,
    ),
    "general": SubagentType(
        name="general",
        prompt="core/agent/subagent.general.txt",
        # 对齐 OpenCode general：全量工具但禁 task（防嵌套/防旁路）
        tools=tuple(t for t in REACT_FULL_TOOLS if t != "task"),
        description="通用子代理，执行多步骤子任务",
        readonly=False,
        allow_nested_task=False,
    ),
    "reviewer": SubagentType(
        name="reviewer",
        prompt="core/agent/subagent.reviewer.txt",
        tools=_face("read", "glob", "grep", "bash", read_only=True),
        description="审核子代理，只读审计不改码",
        readonly=True,
        allow_nested_task=False,
    ),
    "researcher": SubagentType(
        name="researcher",
        prompt="core/agent/subagent.general.txt",
        tools=_face("webfetch", "websearch", "read", read_only=True),
        description="调研子代理，web 搜索与信息收集",
        readonly=True,
        allow_nested_task=False,
    ),
}


def resolve_subagent_type(name: str | None) -> SubagentType:
    """按名称解析子代理类型；未知类型回退到 general（不 fail-fast，容忍模型臆造）。"""
    return SUBTYPES.get(name or "", SUBTYPES["general"])



