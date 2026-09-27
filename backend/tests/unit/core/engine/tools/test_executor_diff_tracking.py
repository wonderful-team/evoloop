"""Executor 级 diff 追踪测试：验证单一写入语义。

同一执行链路（capture → 执行 → compute_and_persist）只落一次 FileOperation，
取代旧的"工具自持 + executor 通用"双写。
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.engine.hooks import hook_system
from app.core.engine.hooks.schemas import HookResult
from app.core.engine.state.base import AgentState
from app.core.engine.tools.executor import AgentToolExecutor
from app.utils.diff import diff_tracker


def _mutating_tool(name="fake_edit"):
    tool = type("FakeTool", (), {})()
    tool.name = name
    tool.metadata = {"is_state_mutating": True, "affected_path_keys": ["path"]}
    return tool


async def _execute_write(_tool, tool_args, **_kwargs):
    path = tool_args["path"]
    with open(path, "w", encoding="utf-8") as f:
        f.write(tool_args["content"])
    return "written"


@pytest.fixture
def _executor_env():
    diff_tracker.clear()
    yield
    diff_tracker.clear()


@pytest.mark.asyncio
async def test_executor_single_write_for_mutating_tool(tmp_path, _executor_env):
    """执行链路对 mutating 工具：恰好落一次 FileOperation（无双写）。"""
    target = tmp_path / "f.txt"
    target.write_text("before\n", encoding="utf-8")

    config = {
        "configurable": {
            "thread_id": "t-1",
            "member_id": 1,
            "project_id": 9,
            "run_id": "r-1",
        },
        "metadata": {"project_id": 9},
    }
    executor = AgentToolExecutor(
        tool_map={"fake_edit": _mutating_tool()},
        state=AgentState(),
        config=config,
    )
    executor._tool_executor = AsyncMock()
    executor._tool_executor.execute = _execute_write

    with (
        patch.object(
            hook_system, "trigger", AsyncMock(return_value=HookResult(success=True))
        ),
        patch("app.core.engine.callbacks.bridge._get_callbacks", return_value=[]),
        patch(
            "app.core.tools.registry.get_tool_affected_paths",
            return_value=[str(target)],
        ),
        patch(
            "app.core.tools.registry.get_tool_map",
            return_value={"fake_edit": _mutating_tool()},
        ),
        patch(
            "app.core.engine.tasks.run_persist_file_operation",
            new=AsyncMock(return_value=None),
        ) as mock_persist,
        patch(
            "app.core.file.tools.utils.resolve_and_validate_path",
            new=AsyncMock(side_effect=lambda path, config: path),
        ),
    ):
        await executor.execute_tool(
            tool_name="fake_edit",
            tool_args={"path": str(target), "content": "after\n"},
            tool_id="call-1",
            local_tool_history=[],
        )

    # 单次执行 → 单次落库
    mock_persist.assert_awaited_once()
    kwargs = mock_persist.await_args.kwargs
    assert kwargs["operation"] == "EDIT"
    assert kwargs["original_content"] == "before\n"
    assert kwargs["file_path"] == str(target)
    assert kwargs["tool_call_id"] == "call-1"


@pytest.mark.asyncio
async def test_executor_no_persist_without_change(tmp_path, _executor_env):
    """执行后文件未变化 → 不落库（无空 diff 行）。"""
    target = tmp_path / "f.txt"
    target.write_text("same\n", encoding="utf-8")

    config = {
        "configurable": {"thread_id": "t-1", "run_id": "r-1"},
        "metadata": {"project_id": 9},
    }
    executor = AgentToolExecutor(
        tool_map={"fake_edit": _mutating_tool()},
        state=AgentState(),
        config=config,
    )
    executor._tool_executor = AsyncMock()

    async def _noop_execute(_tool, _tool_args, **_kwargs):
        return "noop"

    executor._tool_executor.execute = _noop_execute

    with (
        patch.object(
            hook_system, "trigger", AsyncMock(return_value=HookResult(success=True))
        ),
        patch("app.core.engine.callbacks.bridge._get_callbacks", return_value=[]),
        patch(
            "app.core.tools.registry.get_tool_affected_paths",
            return_value=[str(target)],
        ),
        patch(
            "app.core.tools.registry.get_tool_map",
            return_value={"fake_edit": _mutating_tool()},
        ),
        patch(
            "app.core.engine.tasks.run_persist_file_operation",
            new=AsyncMock(return_value=None),
        ) as mock_persist,
        patch(
            "app.core.file.tools.utils.resolve_and_validate_path",
            new=AsyncMock(side_effect=lambda path, config: path),
        ),
    ):
        await executor.execute_tool(
            tool_name="fake_edit",
            tool_args={"path": str(target), "content": "same\n"},
            tool_id="call-1",
            local_tool_history=[],
        )

    mock_persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_executor_does_not_track_non_mutating(tmp_path, _executor_env):
    """非 mutating 工具（read_file）不触发 diff 追踪。"""
    target = tmp_path / "f.txt"
    target.write_text("x\n", encoding="utf-8")

    tool = _mutating_tool("fake_read")
    tool.metadata["is_state_mutating"] = False

    config = {
        "configurable": {"thread_id": "t-1", "run_id": "r-1"},
        "metadata": {"project_id": 9},
    }
    executor = AgentToolExecutor(
        tool_map={"fake_read": tool},
        state=AgentState(),
        config=config,
    )
    executor._tool_executor = AsyncMock()
    executor._tool_executor.execute = AsyncMock(return_value="content")

    with (
        patch.object(
            hook_system, "trigger", AsyncMock(return_value=HookResult(success=True))
        ),
        patch("app.core.engine.callbacks.bridge._get_callbacks", return_value=[]),
        patch(
            "app.core.engine.tasks.run_persist_file_operation",
            new=AsyncMock(return_value=None),
        ) as mock_persist,
        patch(
            "app.core.file.tools.utils.resolve_and_validate_path",
            new=AsyncMock(side_effect=lambda path, config: path),
        ),
    ):
        await executor.execute_tool(
            tool_name="fake_read",
            tool_args={"path": str(target)},
            tool_id="call-1",
            local_tool_history=[],
        )

    mock_persist.assert_not_awaited()


def _base_config(thread_id="t-1"):
    return {
        "configurable": {
            "thread_id": thread_id,
            "member_id": 1,
            "project_id": 9,
            "run_id": "r-1",
        },
        "metadata": {"project_id": 9},
    }


@pytest.mark.asyncio
async def test_snapshot_discarded_on_tool_failure(tmp_path, _executor_env):
    """工具执行抛异常：已捕获的快照必须被丢弃（防内存泄漏 / 陈旧复用）。"""
    target = tmp_path / "f.txt"
    target.write_text("before\n", encoding="utf-8")

    executor = AgentToolExecutor(
        tool_map={"fake_edit": _mutating_tool()},
        state=AgentState(),
        config=_base_config(),
    )
    executor._tool_executor = AsyncMock()

    async def _raise(_tool, _tool_args, **_kwargs):
        raise RuntimeError("boom")

    executor._tool_executor.execute = _raise

    with (
        patch.object(
            hook_system, "trigger", AsyncMock(return_value=HookResult(success=True))
        ),
        patch("app.core.engine.callbacks.bridge._get_callbacks", return_value=[]),
        patch(
            "app.core.tools.registry.get_tool_affected_paths",
            return_value=[str(target)],
        ),
        patch(
            "app.core.tools.registry.get_tool_map",
            return_value={"fake_edit": _mutating_tool()},
        ),
    ):
        result = await executor.execute_tool(
            "fake_edit", {"path": str(target), "content": "after\n"}, "call-1", []
        )

    assert "Error executing" in str(result.message.content)
    assert diff_tracker.get_snapshot_count("t-1") == 0


@pytest.mark.asyncio
async def test_snapshot_discarded_on_hitl_interrupt(tmp_path, _executor_env):
    """HITL 中断（工具抛 AgentHumanInterruptException）：快照同样必须丢弃。"""
    from app.core.exceptions import AgentHumanInterruptException

    target = tmp_path / "f.txt"
    target.write_text("before\n", encoding="utf-8")

    executor = AgentToolExecutor(
        tool_map={"fake_edit": _mutating_tool()},
        state=AgentState(),
        config=_base_config(),
    )
    executor._tool_executor = AsyncMock()

    async def _interrupt(_tool, _tool_args, **_kwargs):
        raise AgentHumanInterruptException("req-1", "awaiting approval")

    executor._tool_executor.execute = _interrupt

    with (
        patch.object(
            hook_system, "trigger", AsyncMock(return_value=HookResult(success=True))
        ),
        patch("app.core.engine.callbacks.bridge._get_callbacks", return_value=[]),
        patch(
            "app.core.tools.registry.get_tool_affected_paths",
            return_value=[str(target)],
        ),
        patch(
            "app.core.tools.registry.get_tool_map",
            return_value={"fake_edit": _mutating_tool()},
        ),
    ):
        with pytest.raises(AgentHumanInterruptException):
            await executor.execute_tool(
                "fake_edit", {"path": str(target), "content": "after\n"}, "call-1", []
            )

    assert diff_tracker.get_snapshot_count("t-1") == 0
