"""Contract tests for tool-message SSE dispatch status/ordering.

Regression guard for the "Agent engine 标准化" refactor (bd2bfe1b) which changed
the final tool-output SSE block from ``status="completed"`` to ``status="streaming"``.
That left tool rows stuck in the streaming state in the desktop UI, and the next
tool's running block then collapsed into the stale streaming row (chatStore
streamIdx merge), hiding earlier tool messages and squeezing AI messages together.

The contract enforced here:

1. ``handle_tool_start`` dispatches a ``running`` tool block (blank content).
2. ``handle_tool_output`` dispatches the tool result blocks with
   ``status="completed"`` — never ``"streaming"`` — so the UI settles on the
   final summary.
3. Hidden tools produce no dispatch at all.
4. Transient tool outputs (skip_message_persistence) still stream to the
   frontend but settle as ``completed``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.core.engine.message.handler import MessageHandler


def _make_handler(**kwargs) -> MessageHandler:
    handler = MessageHandler(
        thread_id=kwargs.get("thread_id", "t-1"),
        project_id=kwargs.get("project_id", 1),
        run_id=kwargs.get("run_id", "r-1"),
        member_id=kwargs.get("member_id", 0),
    )
    # Replace persistence with a mock so no DB is touched.
    handler._repository = AsyncMock()
    handler._repository.resolve_tool_input.return_value = {}
    handler._repository.get_last_message_id.return_value = None
    handler._repository.update.return_value = "msg-1"
    handler._repository.persist.return_value = ("msg-1", 42)
    # Capture outbound blocks instead of real channel delivery.
    handler._publisher = AsyncMock()
    return handler


def _captured_blocks(handler) -> list:
    calls = handler._publisher.publish.call_args_list
    return [call.args[0] for call in calls]


def _captured_actions(handler) -> list:
    calls = handler._publisher.publish.call_args_list
    return [call.kwargs.get("action") or "create" for call in calls]


async def test_tool_start_dispatches_running_block():
    handler = _make_handler()
    result = await handler.handle_tool_start(
        tool_name="shell_exec",
        tool_call_id="call-1",
        input_data={"cmd": "ls"},
    )

    assert result.streamed is True
    assert result.persisted is True
    assert result.message_id == "msg-1"
    assert result.sequence_number == 42

    blocks = _captured_blocks(handler)
    assert len(blocks) == 1
    block = blocks[0]
    assert block.role == "tool"
    assert block.status == "running"
    # Running blocks carry blank content — the UI only needs metadata.
    assert block.content == ""
    assert block.tool_name == "shell_exec"
    assert block.tool_call_id == "call-1"
    assert block.id == "msg-1"
    assert block.sequence_number == 42


async def test_tool_start_includes_resolved_affected_paths():
    """UI 展示契约：tool_meta 带后端解析的实际受影响路径（与 affected_path_keys 解耦）。

    覆盖 affected_path_keys（file 工具）——前端据此展示"工具在操作哪个文件"。
    """
    handler = _make_handler()
    result = await handler.handle_tool_start(
        tool_name="file",
        tool_call_id="call-1",
        input_data={"action": "edit", "path": "src/main.py", "target": "x", "replacement": "y"},
    )
    assert result.persisted is True

    persisted_kwargs = handler._repository.persist.await_args.kwargs
    tool_meta = persisted_kwargs["metadata"]["tool_meta"]
    assert tool_meta["affected_paths"] == ["src/main.py"]
    # file facade 合并六件套后声明面为 path/source/destination 并集，
    # 实际受影响路径由 get_tool_affected_paths 按 action 过滤
    assert tool_meta["affected_path_keys"] == ["path", "source", "destination"]


async def test_tool_start_affected_paths_via_extractor():
    """bash 无 affected_path_keys，但经 affected_path_extractor
    解析出的路径同样进入 affected_paths（此前前端看不到其操作文件）。"""
    handler = _make_handler()
    result = await handler.handle_tool_start(
        tool_name="bash",
        tool_call_id="call-2",
        input_data={"command": "rm -rf /tmp/x"},
    )
    assert result.persisted is True

    persisted_kwargs = handler._repository.persist.await_args.kwargs
    tool_meta = persisted_kwargs["metadata"]["tool_meta"]
    assert tool_meta["affected_paths"] == ["/tmp/x"]


async def test_tool_output_dispatches_completed_blocks_never_streaming():
    """The regression: final tool blocks must settle to 'completed', not 'streaming'."""
    handler = _make_handler()
    result = await handler.handle_tool_output(
        tool_name="shell_exec",
        output="command output text",
        tool_call_id="call-1",
        sequence_number=42,
    )

    assert result.persisted is True

    blocks = _captured_blocks(handler)
    actions = _captured_actions(handler)

    # 修复后：只发一次 completed 块，summary content + metadata（含完整
    # output）一并推给前端，不再重复发 action="update" 的完整输出块。
    assert len(blocks) == 1
    block = blocks[0]
    assert block.role == "tool"
    assert block.id == "msg-1"
    assert block.sequence_number == 42
    # The core contract: NO dispatched tool block may be "streaming".
    assert block.status != "streaming"
    assert block.status == "completed"
    assert actions == ["create"]

    # DB row updated to completed exactly once.
    handler._repository.update.assert_awaited_once()
    update_kwargs = handler._repository.update.await_args.kwargs
    assert update_kwargs["status"] == "completed"
    assert update_kwargs["sequence_number"] == 42


async def test_hidden_tool_dispatches_nothing():
    """Hidden tools (internal_tool_call) never reach the UI."""
    from types import SimpleNamespace
    from unittest.mock import patch

    import app.core.engine.message.handler.tool_mixin as tm

    handler = _make_handler()
    with patch.object(tm, "get_tool_metadata") as mock_meta:
        mock_meta.return_value = SimpleNamespace(
            is_hidden=True,
            get_display_name=lambda n, a=None: "Hidden",
            affected_path_keys=[],
        )
        result = await handler.handle_tool_output(
            tool_name="hidden_tool",
            output="secret output",
            tool_call_id="call-h",
            sequence_number=7,
        )

    assert result.persisted is False
    assert result.streamed is False
    assert _captured_blocks(handler) == []
    handler._repository.update.assert_not_called()
    handler._repository.persist.assert_not_called()


async def test_transient_tool_output_streams_but_settles_completed():
    """Transient tool messages (skip_message_persistence) still stream to the
    frontend but must settle on 'completed' — not stay stuck 'streaming'."""
    handler = _make_handler()
    output = type("Out", (), {"meta": {"skip_message_persistence": True}})()
    result = await handler.handle_tool_output(
        tool_name="transient_tool",
        output=output,
        tool_call_id="call-t",
        sequence_number=0,
    )

    assert result.persisted is False
    assert result.streamed is True
    blocks = _captured_blocks(handler)
    assert len(blocks) == 1
    assert blocks[0].status == "completed"
    handler._repository.persist.assert_not_called()
    handler._repository.update.assert_not_called()
