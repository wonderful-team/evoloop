"""EngineRuntime 协议、装配与引擎侧实现行为测试。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.hitl.engine_runtime import (
    EngineRuntime,
    get_runtime,
    register_engine_runtime,
    reset_engine_runtime,
)


def test_protocol_accepts_engine_impl():
    from app.core.engine.hitl_runtime import HitlEngineRuntime

    assert isinstance(HitlEngineRuntime(), EngineRuntime)


def test_register_then_get_returns_same_instance():
    fake = MagicMock()
    try:
        register_engine_runtime(fake)
        assert get_runtime() is fake
    finally:
        reset_engine_runtime()


def test_get_runtime_assembles_engine_impl_when_unregistered():
    """未注册时惰性装配真实引擎实现（唯一装配边）。"""
    from app.core.engine.hitl_runtime import HitlEngineRuntime

    try:
        reset_engine_runtime()
        rt = get_runtime()
        assert isinstance(rt, HitlEngineRuntime)
    finally:
        reset_engine_runtime()


def _push(rt, **overrides):
    kwargs = {
        "thread_id": "t-1",
        "project_id": 1,
        "run_id": None,
        "request_type": "approval",
        "prompt": "approve?",
        "request_id": "req-1",
        "options": None,
        "context": None,
        "default_value": None,
        "tool_call_id": "call-1",
        "tool_name": "ask_confirm",
        "parent_id": None,
        "metadata": None,
    }
    kwargs.update(overrides)
    rt.push_hitl_request(**kwargs)


@pytest.mark.asyncio
async def test_push_hitl_request_suppresses_subagent_channel():
    """subagent 透传：请求落库但 suppress_user_push=True（不推用户通道）。"""
    from app.core.engine.hitl_runtime import HitlEngineRuntime

    with (
        patch("app.core.engine.hitl_runtime.ContextManager") as mock_ctx_cls,
        patch("app.core.engine.hitl_runtime.MessageHandler") as mock_handler_cls,
    ):
        mock_ctx_cls.current.return_value = MagicMock(
            metadata={"task_type": "subagent"}
        )
        handler = mock_handler_cls.return_value
        handler.handle_hitl_request = AsyncMock()

        _push(HitlEngineRuntime())
        await asyncio.sleep(0)

    mock_handler_cls.assert_called_once_with(thread_id="t-1", project_id=1, run_id=None)
    kwargs = handler.handle_hitl_request.await_args.kwargs
    assert kwargs["suppress_user_push"] is True
    assert kwargs["tool_call_id"] == "call-1"
    assert kwargs["tool_name"] == "ask_confirm"
    assert kwargs["request_id"] == "req-1"


@pytest.mark.asyncio
async def test_push_hitl_request_main_session_not_suppressed():
    from app.core.engine.hitl_runtime import HitlEngineRuntime

    with (
        patch("app.core.engine.hitl_runtime.ContextManager") as mock_ctx_cls,
        patch("app.core.engine.hitl_runtime.MessageHandler") as mock_handler_cls,
    ):
        mock_ctx_cls.current.return_value = MagicMock(metadata={})
        handler = mock_handler_cls.return_value
        handler.handle_hitl_request = AsyncMock()

        _push(HitlEngineRuntime())
        await asyncio.sleep(0)

    kwargs = handler.handle_hitl_request.await_args.kwargs
    assert kwargs["suppress_user_push"] is False


@pytest.mark.asyncio
async def test_close_hitl_message_updates_by_tool_call_id():
    from app.core.engine.hitl_runtime import HitlEngineRuntime

    with patch("app.core.engine.hitl_runtime.MessageRepository") as mock_repo_cls:
        repo = mock_repo_cls.return_value
        repo.update_status_by_tool_call_id = AsyncMock(return_value=True)

        ok = await HitlEngineRuntime().close_hitl_message("t-1", "call-1", "completed")

    assert ok is True
    mock_repo_cls.assert_called_once_with(thread_id="t-1")
    repo.update_status_by_tool_call_id.assert_awaited_once_with("call-1", "completed")


@pytest.mark.asyncio
async def test_persist_hitl_user_message_writes_human_and_updates_tool_result():
    """human 落库语义：role=human + 实时推送 + 更新原 tool 结果。"""
    from app.core.engine.hitl_runtime import HitlEngineRuntime

    with (
        patch("app.core.engine.hitl_runtime.MessageRepository") as mock_repo_cls,
        patch("app.core.engine.hitl_runtime.MessageBlockFactory") as mock_factory_cls,
        patch("app.core.engine.hitl_runtime.MessagePublisher") as mock_pub_cls,
    ):
        repo = AsyncMock()
        repo.persist = AsyncMock(return_value=("msg-h-1", 3))
        repo.update_tool_result_by_tool_call_id = AsyncMock()
        mock_repo_cls.return_value = repo
        block = mock_factory_cls.from_event.return_value
        publisher = mock_pub_cls.return_value
        publisher.publish = AsyncMock()

        await HitlEngineRuntime().persist_hitl_user_message(
            thread_id="t-1",
            project_id=120,
            member_id=7,
            tool_call_id="call-1",
            user_content="yes",
            final_result="done",
        )

    mock_repo_cls.assert_called_once_with("t-1", 120, member_id=7)
    repo.persist.assert_awaited_once_with(
        role="human", content="yes", category="user",
        action_type="text", status="completed",
    )
    mock_factory_cls.from_event.assert_called_once_with(
        thread_id="t-1", sequence_number=3, role="human", content="yes",
        category="user", status="completed", message_id="msg-h-1",
    )
    publisher.publish.assert_awaited_once_with(block)
    repo.update_tool_result_by_tool_call_id.assert_awaited_once_with("call-1", "done")


@pytest.mark.asyncio
async def test_persist_hitl_user_message_skips_publish_when_no_content():
    from app.core.engine.hitl_runtime import HitlEngineRuntime

    with (
        patch("app.core.engine.hitl_runtime.MessageRepository") as mock_repo_cls,
        patch("app.core.engine.hitl_runtime.MessageBlockFactory") as mock_factory_cls,
    ):
        repo = AsyncMock()
        mock_repo_cls.return_value = repo

        await HitlEngineRuntime().persist_hitl_user_message(
            thread_id="t-1", project_id=120, member_id=7,
            tool_call_id="call-1", user_content=None, final_result="no",
        )

    repo.persist.assert_not_awaited()
    mock_factory_cls.from_event.assert_not_called()
    repo.update_tool_result_by_tool_call_id.assert_awaited_once_with("call-1", "no")


@pytest.mark.asyncio
async def test_execute_tool_builds_state_and_reexecutes_with_worker_tools():
    from app.core.engine.hitl_runtime import HitlEngineRuntime

    with (
        patch("app.core.engine.hitl_runtime.tool_manager") as mock_tm,
        patch("app.core.engine.hitl_runtime.AgentToolExecutor") as mock_exec_cls,
    ):
        wrapper = MagicMock()
        wrapper.name = "list_dir"
        mock_tm.get_agent_tools = AsyncMock(return_value=[wrapper])
        executor = mock_exec_cls.return_value
        executor.execute_tool = AsyncMock(
            return_value=type(
                "ExecResult", (), {"message": type("Msg", (), {"content": "ok"})()}
            )()
        )

        result = await HitlEngineRuntime().execute_tool(
            tool_name="list_dir",
            tool_args={"path": "/tmp/x"},
            tool_call_id="call-1",
            config={"configurable": {"thread_id": "t-1"}, "metadata": {"project_id": 120}},
        )

    assert result == "ok"
    exec_kwargs = mock_exec_cls.call_args.kwargs
    assert exec_kwargs["state"].thread_id == "t-1"
    assert exec_kwargs["state"].project_id == 120
    assert exec_kwargs["config"] == {
        "configurable": {"thread_id": "t-1"}, "metadata": {"project_id": 120},
    }
    assert exec_kwargs["name"] == "HITLResume"
    mock_tm.get_agent_tools.assert_awaited_once_with("react", exec_kwargs["state"])
    executor.execute_tool.assert_awaited_once_with("list_dir", {"path": "/tmp/x"}, "call-1", [])


@pytest.mark.asyncio
async def test_execute_tool_reuses_provided_state():
    from app.core.engine.hitl_runtime import HitlEngineRuntime
    from app.core.engine.state import AgentState

    state = AgentState(thread_id="t-2", project_id=99)
    with patch("app.core.engine.hitl_runtime.AgentToolExecutor") as mock_exec_cls:
        mock_exec_cls.return_value.execute_tool = AsyncMock(
            return_value=type(
                "ExecResult", (), {"message": type("Msg", (), {"content": "ok"})()}
            )()
        )
        await HitlEngineRuntime().execute_tool(
            tool_name="t", tool_args={}, tool_call_id="c", config={}, state=state
        )

    assert mock_exec_cls.call_args.kwargs["state"] is state
