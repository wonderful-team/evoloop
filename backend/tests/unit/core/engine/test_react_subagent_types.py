"""Subagent type registry + tool-isolation + persona injection tests (对齐 OpenCode).

- 每个子代理类型定义人格 prompt + 工具面（visibleTools 语义）。
- explore/reviewer/researcher 只读（无 edit/write/task）。
- general 全量但禁 task（防嵌套/防旁路）。
- loop 层按 subagent_tools 裁剪 react 工具池。
- build_system_prompt 在子代理模式下使用类型专属人格而非 main.txt。
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.engine.react.subagent import types as subagent_types
from app.core.engine.sdk_adapter.tools import build_sdk_tools
from app.core.engine.state import AgentState


def test_subtypes_all_have_persona_and_nonempty_face():
    for name, st in subagent_types.SUBTYPES.items():
        assert st.prompt, f"{name} must define a persona prompt"
        assert st.tools, f"{name} must define a non-empty tool face"
        assert set(st.tools).issubset(set(subagent_types.REACT_FULL_TOOLS))


def test_readonly_types_exclude_state_mutating_tools():
    mutating = {"edit", "write", "task", "macro", "run_macro", "plan"}
    for name in ("explore", "reviewer", "researcher"):
        st = subagent_types.SUBTYPES[name]
        assert st.readonly is True
        assert not (set(st.tools) & mutating), f"{name} must not expose {mutating & set(st.tools)}"


def test_general_denies_task_but_allows_write():
    st = subagent_types.SUBTYPES["general"]
    assert st.readonly is False
    assert "task" not in st.tools
    assert "edit" in st.tools
    assert "write" in st.tools


def test_resolve_unknown_type_falls_back_to_general():
    st = subagent_types.resolve_subagent_type("nope")
    assert st.name == "general"
    assert subagent_types.resolve_subagent_type(None).name == "general"


def test_unknown_type_is_not_present_when_name_given():
    st = subagent_types.resolve_subagent_type("explore")
    assert st.name == "explore"


NS = SimpleNamespace


async def test_subagent_tool_face_is_sliced_by_metadata(monkeypatch) -> None:
    """run_agent_loop 的子代理工具面裁剪在 build_sdk_tools 按 subagent_tools 生效。"""
    captured: dict = {}

    class _FakeManager:
        async def get_agent_tools(self, agent, state):
            captured["agent"] = agent
            from types import SimpleNamespace

            return [SimpleNamespace(name="bash"), SimpleNamespace(name="read")]

    monkeypatch.setattr("app.core.tools.manager.tool_manager", _FakeManager())
    from app.core.engine.sdk_adapter import tools as sdk_tools_mod

    monkeypatch.setattr(
        sdk_tools_mod,
        "_build_sdk_tool",
        lambda tool, **_: SimpleNamespace(
            name=str(tool.name), executor=SimpleNamespace()
        ),
    )

    specs = await build_sdk_tools(
        AgentState(thread_id="sub", messages=[]),
        {"configurable": {"thread_id": "sub"}, "metadata": {"subagent_tools": ["read"]}},
        loop=asyncio.get_running_loop(),
        tool_history=[],
        conversation_id="c",
    )
    assert captured["agent"] == "react"
    assert [spec.name for spec in specs] == ["read"]  # SDKToolSpec 列表


async def test_build_system_prompt_uses_subagent_persona():
    from app.core.context.manager import ContextManager, EvoContext
    from app.core.engine.react.prompts import build_system_prompt

    ctx = EvoContext(thread_id="sub", project_id=7, metadata={"source": "web"})
    ctx.metadata.subagent_prompt = "core/agent/subagent.explore.txt"

    with (
        ContextManager.use(ctx),
        patch("app.core.engine.react.prompts.prompt_exists", return_value=True) as pe,
        patch("app.core.engine.react.prompts.render_prompt", return_value="EXPLORE-PERSONA") as rp,
        patch("app.core.engine.react.prompts._capability_index_async", AsyncMock(return_value="")),
        patch("app.core.engine.react.prompts._memory_block", return_value=""),
        patch("app.core.engine.react.prompts._environment_block", return_value=""),
    ):
        out = await build_system_prompt(NS(), cfg_with_meta())

    assert out == "EXPLORE-PERSONA"
    pe.assert_called_once_with("core/agent/subagent.explore.txt")
    assert rp.call_args.args[0] == "core/agent/subagent.explore.txt"


def cfg_with_meta() -> dict:
    return {"metadata": {"subagent_prompt": "core/agent/subagent.explore.txt"}}


async def test_spawn_subagent_threads_tool_face_persona_and_task_type():
    """spawner 把子代理类型解析出的工具面/人格/task_type 注入子代理 metadata。"""
    from app.core.context.manager import ContextManager, EvoContext
    from app.core.engine.react.subagent.spawner import spawn_subagent

    with (
        patch("app.core.engine.react.subagent.spawner.run_agent_background", AsyncMock()) as run_mock,
        patch("app.core.engine.react.subagent.spawner._read_subagent_result", AsyncMock(return_value="r")),
    ):
        with ContextManager.use(EvoContext(thread_id="parent", project_id=7, metadata={"source": "web"})):
            await spawn_subagent(
                {"subagent_type": "explore", "description": "搜", "prompt": "p"}, {"metadata": {}}
            )

    _, inputs = run_mock.await_args.args
    assert inputs.metadata["task_type"] == "subagent"
    assert inputs.metadata["subagent_prompt"] == "core/agent/subagent.explore.txt"
    assert "edit" not in inputs.metadata["subagent_tools"]
    assert "read" in inputs.metadata["subagent_tools"]


async def test_build_ctx_syncs_subagent_fields_to_ctx_metadata():
    """build_ctx 把子代理/A2A 语义字段同步到 ctx.metadata（供 R3 通道策略判定）。"""
    from app.core.context.manager import EvoContext
    from app.core.engine.agent.models import BackgroundAgentInputs
    from app.core.engine.runner_base import build_ctx

    inputs = BackgroundAgentInputs(
        messages=[],
        project_id=7,
        metadata={
            "task_type": "subagent",
            "subagent_type": "explore",
            "subagent_tools": ["read"],
            "subagent_prompt": "core/agent/subagent.explore.txt",
            "is_subagent": True,
        },
    )

    fresh = EvoContext(thread_id="sub", project_id=7)
    with (
        patch("app.core.engine.runner_base.ContextManager.load", AsyncMock(return_value=fresh)),
        patch("app.core.engine.runner_base.ContextManager.set"),
        patch(
            "app.core.engine.runner_base.thread_context_store.get_working_directory",
            return_value=None,
        ),
    ):
        ctx = await build_ctx("sub", inputs, run_id="r")

    assert ctx.metadata.task_type == "subagent"
    assert ctx.metadata.is_subagent is True
    assert ctx.metadata.subagent_type == "explore"
    assert ctx.metadata.subagent_tools == ["read"]
