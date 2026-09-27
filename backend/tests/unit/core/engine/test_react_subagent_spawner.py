"""React subagent spawner unit tests — no DB, no real LLM.

Covers ``spawn_subagent`` input mapping / sub-thread id format / background
dispatch, plus ``_read_subagent_result`` DB query paths (faked session).
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.context.manager import ContextManager, EvoContext


class _FakeSession:
    def __init__(self, rows=None, raise_on_execute=False):
        self._rows = rows or []
        self._raise = raise_on_execute

    async def execute(self, stmt):
        if self._raise:
            raise RuntimeError("db exploded")
        return self

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _scope_factory(session):
    @asynccontextmanager
    async def scope():
        yield session

    return scope


def _ctx() -> EvoContext:
    return EvoContext(thread_id="parent", project_id=7, metadata={"source": "web"})


def _config() -> dict:
    return {"configurable": {"thread_id": "parent", "model": "doubao-seed"}, "metadata": {}}


@pytest.mark.asyncio
async def test_spawn_subagent_maps_inputs_and_dispatches():
    from app.core.engine.agent.models import BackgroundAgentInputs
    from app.core.engine.react.subagent.spawner import spawn_subagent

    run_mock = AsyncMock()
    read_mock = AsyncMock(return_value="child done")

    with (
        patch("app.core.engine.react.subagent.spawner.run_agent_background", run_mock),
        patch("app.core.engine.react.subagent.spawner._read_subagent_result", read_mock),
    ):
        with ContextManager.use(_ctx()):
            result = await spawn_subagent(
                {"subagent_type": "explore", "description": "文件搜索", "prompt": "请搜索", "id": "cid1"},
                _config(),
            )

    assert result["name"] == "task"
    assert result["tool_call_id"] == "cid1"
    assert result["content"] == "[explore subagent] 文件搜索\n\nchild done"

    sub_tid, inputs = run_mock.await_args.args
    assert sub_tid.startswith("parent-react-sub-")
    assert isinstance(inputs, BackgroundAgentInputs)
    assert inputs.messages == [{"type": "human", "content": "请搜索"}]
    assert inputs.project_id == 7
    assert inputs.model == "doubao-seed"
    assert inputs.goal == "文件搜索"
    assert inputs.session_goal == "文件搜索"
    assert inputs.metadata["is_subagent"] is True
    assert inputs.metadata["subagent_type"] == "explore"
    assert inputs.metadata["source"] == "web"
    assert inputs.metadata["initial_node"] == "react"

    read_mock.assert_awaited_once_with(sub_tid)


@pytest.mark.asyncio
async def test_spawn_subagent_defaults_to_general():
    from app.core.engine.react.subagent.spawner import spawn_subagent

    with (
        patch("app.core.engine.react.subagent.spawner.run_agent_background", AsyncMock()),
        patch(
            "app.core.engine.react.subagent.spawner._read_subagent_result",
            AsyncMock(return_value=""),
        ),
    ):
        with ContextManager.use(_ctx()):
            result = await spawn_subagent({}, {
                "configurable": {"model": None, "thread_id": "parent"},
                "metadata": {},
            })

    assert result["content"] == "[general subagent] general\n\n"


@pytest.mark.asyncio
async def test_spawn_subagent_agent_alias_and_task_prompt():
    from app.core.engine.react.subagent.spawner import spawn_subagent

    with (
        patch("app.core.engine.react.subagent.spawner.run_agent_background", AsyncMock()) as run_mock,
        patch(
            "app.core.engine.react.subagent.spawner._read_subagent_result",
            AsyncMock(return_value="x"),
        ),
    ):
        with ContextManager.use(_ctx()):
            await spawn_subagent(
                {"agent": "reviewer", "task": "审代码"}, _config()
            )

    sub_tid, inputs = run_mock.await_args.args
    assert inputs.messages[0]["content"] == "审代码"
    assert inputs.goal == "reviewer"
    assert inputs.metadata["subagent_type"] == "reviewer"
    assert sub_tid.startswith("parent-react-sub-")
    assert len(sub_tid) == len("parent-react-sub-") + 6


@pytest.mark.asyncio
async def test_spawn_subagent_background_failure_still_reads_result():
    from app.core.engine.react.subagent.spawner import spawn_subagent

    with (
        patch(
            "app.core.engine.react.subagent.spawner.run_agent_background",
            AsyncMock(side_effect=RuntimeError("dispatch failed")),
        ),
        patch(
            "app.core.engine.react.subagent.spawner._read_subagent_result",
            AsyncMock(return_value="partial"),
        ) as read_mock,
    ):
        with ContextManager.use(_ctx()):
            result = await spawn_subagent({}, _config())

    assert "partial" in result["content"]
    read_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_spawn_subagent_thread_id_from_config_when_context_empty():
    from app.core.engine.react.subagent.spawner import spawn_subagent

    with (
        patch("app.core.engine.react.subagent.spawner.run_agent_background", AsyncMock()) as run_mock,
        patch("app.core.engine.react.subagent.spawner._read_subagent_result", AsyncMock(return_value="")),
    ):
        with ContextManager.use(EvoContext()):
            await spawn_subagent({}, _config())

    assert run_mock.await_args.args[0].startswith("parent-react-sub-")


# ---------------------------------------------------------------------------
# _read_subagent_result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_subagent_result_returns_first_ai_text():
    from app.core.engine.react.subagent.spawner import _read_subagent_result

    rows = [
        SimpleNamespace(role="tool", content="out"),
        SimpleNamespace(role="ai", content="最终结果"),
        SimpleNamespace(role="assistant", content="另一个"),
        SimpleNamespace(role="ai", content=""),
    ]
    session = _FakeSession(rows=rows)
    with patch("app.infrastructure.database.session_scope", _scope_factory(session)):
        text = await _read_subagent_result("sub")

    assert text == "最终结果"


@pytest.mark.asyncio
async def test_read_subagent_result_no_visible_text():
    from app.core.engine.react.subagent.spawner import _read_subagent_result

    rows = [SimpleNamespace(role="tool", content="out"), SimpleNamespace(role="ai", content="")]
    with patch("app.infrastructure.database.session_scope", _scope_factory(_FakeSession(rows))):
        text = await _read_subagent_result("sub")
    assert text == "（子代理未返回可见结果）"


@pytest.mark.asyncio
async def test_read_subagent_result_db_failure_returns_fallback():
    from app.core.engine.react.subagent.spawner import _read_subagent_result

    session = _FakeSession(raise_on_execute=True)
    with patch("app.infrastructure.database.session_scope", _scope_factory(session)):
        text = await _read_subagent_result("sub")
    assert text == "（子代理结果读取失败）"
