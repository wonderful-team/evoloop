"""
测试 evoloop_tool 装饰器的完整 tuple 支持：
1. 工具返回 tuple → 装饰器拆分为 ToolResult
2. ToolResult 附带 display_name 和 meta
3. MessageHandler 从 ToolResult 读取 display_name
"""
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import asyncio


async def test_decorator_renders_display_name():
    """验证装饰器自动渲染 display_name 并附在 ToolResult 上"""
    from app.core.tools.base import evoloop_tool

    @evoloop_tool(
        summary_template="evoloop_logger.list_summary"
    )
    async def mock_list(path: str = ".") -> str:
        """Mock list tool."""
        return "file1.py\nfile2.py", {"count": 2}

    result = await mock_list.ainvoke({"path": "src/"})

    # 应该是 ToolResult（str 子类）
    from app.core.tools.base import ToolResult
    assert isinstance(result, ToolResult), f"Expected ToolResult, got: {type(result)}"

    # Agent 看到的是纯文本
    assert result == "file1.py\nfile2.py"

    # 附带 display_name（i18n key 或已渲染）
    assert isinstance(result.display_name, str) and len(result.display_name) > 0, f"Got: {result.display_name}"

    # 附带 meta
    assert result.meta.get("count") == 2

    print("✅ test_decorator_renders_display_name passed")


async def test_decorator_with_missing_count():
    """验证 count 缺失时可选块消失"""
    from app.core.tools.base import evoloop_tool

    @evoloop_tool(
        summary_template="evoloop_logger.list_summary"
    )
    async def mock_list_no_count(path: str = ".") -> str:
        """Mock list tool without count."""
        return "file1.py", {}

    result = await mock_list_no_count.ainvoke({"path": "src/"})

    from app.core.tools.base import ToolResult
    assert isinstance(result, ToolResult)
    assert isinstance(result.display_name, str) and len(result.display_name) > 0, f"Got: {result.display_name}"

    print("✅ test_decorator_with_missing_count passed")


async def test_handler_reads_from_tool_result():
    """验证 MessageHandler 从 ToolResult 读取 display_name"""
    from app.core.engine.message.handler import MessageHandler
    from app.core.tools.base import ToolResult

    handler = MessageHandler(thread_id="test-thread", project_id=1)

    mock_repo = MagicMock()
    mock_repo.resolve_tool_input = AsyncMock(return_value={"path": "src/"})
    mock_repo.update = AsyncMock(return_value=str(uuid.uuid4()))
    handler._repository = mock_repo

    mock_meta = MagicMock()
    mock_meta.is_hidden = False
    mock_meta.affected_path_keys = ["path"]
    mock_meta.summary_template = "evoloop_logger.list_summary"

    # 模拟 get_tool_metadata 返回的 metadata
    def capture_display_name(tool_name, args):
        return f"已列出 {args.get('path')} ({args.get('count')} 项)"

    mock_meta.get_display_name = MagicMock(side_effect=capture_display_name)

    with patch('app.core.engine.message.handler.get_tool_metadata', return_value=mock_meta):
        # 构造 ToolResult（模拟装饰器已处理）
        tool_output = ToolResult(
            "file1.py\nfile2.py",
            meta={"count": 2},
            display_name="已列出 src/ (2 项)"
        )

        result = await handler.handle_tool_output(
            tool_name="list_dir",
            output=tool_output,
            tool_call_id="call_123",
            sequence_number=42
        )

    # 验证 update 被调用，且 content 是纯文本
    call_kwargs = mock_repo.update.call_args.kwargs
    stored_content = call_kwargs.get("content")
    assert stored_content == "file1.py\nfile2.py", f"Expected pure text, got: {stored_content}"

    # 验证 meta_data 中的 display_name 正确
    meta_data = call_kwargs.get("meta_data")
    assert meta_data["tool_meta"]["display_name"] == "已列出 src/ (2 项)"

    print("✅ test_handler_reads_from_tool_result passed")


async def test_handler_fallback_without_tool_result():
    """验证普通字符串返回值仍能正常工作（兜底）"""
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

    def capture_display_name(tool_name, args):
        return f"读取文件 '{args.get('path')}'"

    mock_meta.get_display_name = MagicMock(side_effect=capture_display_name)

    with patch('app.core.engine.message.handler.get_tool_metadata', return_value=mock_meta):
        # 普通字符串（未经过 ToolResult 封装）
        tool_output = "[File: main.py]\n\nimport os"

        result = await handler.handle_tool_output(
            tool_name="read_file",
            output=tool_output,
            tool_call_id="call_456",
            sequence_number=43
        )

    call_kwargs = mock_repo.update.call_args.kwargs
    stored_content = call_kwargs.get("content")
    assert stored_content == tool_output

    print("✅ test_handler_fallback_without_tool_result passed")


if __name__ == "__main__":
    asyncio.run(test_decorator_renders_display_name())
    asyncio.run(test_decorator_with_missing_count())
    asyncio.run(test_handler_reads_from_tool_result())
    asyncio.run(test_handler_fallback_without_tool_result())
    print("\n✅ All evoloop_tool tuple tests passed!")
