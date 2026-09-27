"""React engine logic unit tests — no DB, no real LLM.

验证 react 链路的纯逻辑：
1. 统一截断（truncate_output）
2. system prompt 组装（main.txt + 索引 + 通道变体）
3. react 工具池解析（task/macro 注册）
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def test_truncate_output():
    from app.core.engine.react.truncate import truncate_output

    r = truncate_output("short")
    assert r.truncated is False
    assert r.content == "short"

    big = "x" * 40000
    r = truncate_output(big, thread_id="test")
    assert r.truncated is True
    assert r.output_path is not None
    assert len(r.content) < len(big)
    assert "TRUNCATED" in r.content


@pytest.mark.asyncio
async def test_react_prompts_assembly():
    from app.core.context.manager import ContextManager, EvoContext
    from app.core.engine.react.prompts import build_system_prompt
    from app.core.engine.state import AgentState

    ctx = EvoContext(thread_id="t", project_id=0, working_directory="/tmp")
    ctx.metadata.source = "web"
    md = ctx.metadata
    md.active_skills = "- skill1: desc1"
    md.active_macros = "- macro1: desc1"
    md.core_memory_raw = "热记忆"

    state = AgentState(messages=[], thread_id="t")
    with ContextManager.use(ctx):
        sp = await build_system_prompt(
            state, {"configurable": {"thread_id": "t"}, "metadata": {"source": "web"}}
        )
    assert "available_skills" in sp
    assert "available_macros" in sp
    assert "热记忆" in sp
    assert "task" in sp
    assert "{{" not in sp


def test_react_tool_pool():
    from app.core.tools.registry import get_agent_tools

    tools = get_agent_tools("react")
    names = [t.name for t in tools]
    assert "task" in names
    assert "macro" in names
    # 宏收敛为单一 macro 工具（run/create/update/delete/list 一体），面内不应再出现
    # 单独的 run_macro / create_macro。
    assert "run_macro" not in names
    assert "create_macro" not in names
    assert len(names) >= 10


def test_voice_channel_variant():
    from app.core.context.manager import ContextManager, EvoContext
    from app.core.engine.react.prompts import (
        _capability_index,
        _environment_block,
    )

    ctx = EvoContext(thread_id="t", project_id=0, working_directory="/tmp")
    md = ctx.metadata
    md.active_skills = "- skill1: desc1"
    with ContextManager.use(ctx):
        env = _environment_block(ctx, None)
    assert "工作目录" in env
    with ContextManager.use(ctx):
        idx = _capability_index(ctx)
    assert "skill1" in idx
