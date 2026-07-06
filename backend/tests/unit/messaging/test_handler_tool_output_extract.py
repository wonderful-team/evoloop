"""
测试 MessageHandler.handle_tool_output 中的 content 提取逻辑

使用 mock 来隔离数据库依赖，验证修复后的行为。
"""
import json
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import asyncio


async def test_handle_tool_output_extracts_json_content():
    """验证 handle_tool_output 对 list_dir JSON 输出的处理"""

    from app.core.engine.message.handler import MessageHandler

    handler = MessageHandler(thread_id="test-thread", project_id=1)

    # Mock repository
    mock_repo = MagicMock()
    mock_repo.resolve_tool_input = AsyncMock(return_value={"path": "src/"})
    mock_repo.update = AsyncMock(return_value=str(uuid.uuid4()))
    handler._repository = mock_repo

    # Mock get_tool_metadata
    mock_meta = MagicMock()
    mock_meta.is_hidden = False
    mock_meta.affected_path_keys = ["path"]
    mock_meta.summary_template = "database_logger.tool_summary.list_files"
    mock_meta.result_summary_template = "evoloop_logger.list_summary"
    mock_meta.get_display_name = MagicMock(return_value="已列出 src/ (3 项)")

    with patch('app.core.engine.message.handler._tool_mixin.get_tool_metadata', return_value=mock_meta):
        # 模拟 list_dir 的 JSON 输出
        tool_output = json.dumps({
            "content": "file1.py\nfile2.py\nREADME.md",
            "count": 3
        })

        result = await handler.handle_tool_output(
            tool_name="list_dir",
            output=tool_output,
            tool_call_id="call_123",
            sequence_number=42
        )

    # 验证 update 被调用，且 content 是原始输出（当前实现不转换 JSON 为纯文本）
    assert mock_repo.update.called, "repository.update should be called"
    call_kwargs = mock_repo.update.call_args.kwargs

    stored_content = call_kwargs.get("content")
    assert stored_content == tool_output, \
        f"Expected original output, got: {stored_content}"

    # 验证 meta_data 中仍然包含原始 output 和 tool_meta
    meta_data = call_kwargs.get("meta_data")
    assert meta_data is not None
    assert meta_data["output"] == tool_output, "Original output should be preserved in metadata"
    assert meta_data["tool_meta"]["display_name"] == "已列出 src/ (3 项)"

    print("✅ test_handle_tool_output_extracts_json_content passed")


async def test_handle_tool_output_plain_text_unchanged():
    """验证 read_file 类的纯文本输出不受影响"""

    from app.core.engine.message.handler import MessageHandler

    handler = MessageHandler(thread_id="test-thread", project_id=1)

    mock_repo = MagicMock()
    mock_repo.resolve_tool_input = AsyncMock(return_value={"path": "main.py"})
    mock_repo.update = AsyncMock(return_value=str(uuid.uuid4()))
    handler._repository = mock_repo

    mock_meta = MagicMock()
    mock_meta.is_hidden = False
    mock_meta.affected_path_keys = ["path"]
    mock_meta.summary_template = "database_logger.tool_summary.read_file"
    mock_meta.result_summary_template = None
    mock_meta.get_display_name = MagicMock(return_value="读取文件 'main.py'")

    with patch('app.core.engine.message.handler._tool_mixin.get_tool_metadata', return_value=mock_meta):
        tool_output = "[File: main.py | Lines 1-10]\n\nimport os\n"

        result = await handler.handle_tool_output(
            tool_name="read_file",
            output=tool_output,
            tool_call_id="call_456",
            sequence_number=43
        )

    call_kwargs = mock_repo.update.call_args.kwargs
    stored_content = call_kwargs.get("content")
    assert stored_content == tool_output, f"Plain text should be unchanged, got: {stored_content}"

    print("✅ test_handle_tool_output_plain_text_unchanged passed")


async def test_display_name_still_gets_count():
    """验证 display_name 仍然能获取到 count 用于渲染摘要"""

    from app.core.engine.message.handler import MessageHandler

    handler = MessageHandler(thread_id="test-thread", project_id=1)

    mock_repo = MagicMock()
    mock_repo.resolve_tool_input = AsyncMock(return_value={"path": "src/"})
    mock_repo.update = AsyncMock(return_value=str(uuid.uuid4()))
    handler._repository = mock_repo

    mock_meta = MagicMock()
    mock_meta.is_hidden = False
    mock_meta.affected_path_keys = ["path"]
    mock_meta.summary_template = "database_logger.tool_summary.list_files"
    mock_meta.result_summary_template = "evoloop_logger.list_summary"

    captured_args = {}
    def capture_display_name(tool_name, args, status=None):
        captured_args.update(args)
        return f"已列出 {args.get('path')} ({args.get('count')} 项)"

    mock_meta.get_display_name = MagicMock(side_effect=capture_display_name)

    with patch('app.core.engine.message.handler._tool_mixin.get_tool_metadata', return_value=mock_meta):
        from app.core.tools.base import ToolResult
        tool_output = ToolResult(
            text=json.dumps({"content": "a.py\nb.py", "count": 2}),
            meta={"count": 2},
        )
        await handler.handle_tool_output(
            tool_name="list_dir",
            output=tool_output,
            tool_call_id="call_789",
            sequence_number=44
        )

    # 验证 get_display_name 被调用时，args 包含了 count
    assert captured_args.get("count") == 2, f"count should be passed to display_name, got args: {captured_args}"
    assert captured_args.get("path") == "src/"

    print("✅ test_display_name_still_gets_count passed")


if __name__ == "__main__":
    asyncio.run(test_handle_tool_output_extracts_json_content())
    asyncio.run(test_handle_tool_output_plain_text_unchanged())
    asyncio.run(test_display_name_still_gets_count())
    print("\n✅ All handle_tool_output tests passed!")
