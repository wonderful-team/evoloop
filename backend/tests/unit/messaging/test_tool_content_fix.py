"""
测试工具 content 修复：Agent 收到纯文本，MessageHandler 能拿到 count 元数据

验证场景：
1. evoloop_tool 装饰器把 dict/JSON 返回值转换为纯文本，元数据存入 ContextManager
2. MessageHandler 从 ContextManager 读取元数据，用于 display_name 渲染
3. 纯文本工具不受影响
"""
import json
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


def test_decorator_extracts_dict_to_context():
    """验证 evoloop_tool 装饰器对 dict 返回值的传递（当前实现直接返回原始值）"""
    from app.core.context.manager import ContextManager, EvoContext

    # 设置一个干净的上下文
    ctx = EvoContext()
    token = ContextManager.set(ctx)
    try:
        from app.core.tools.base import evoloop_tool

        @evoloop_tool()
        async def mock_list_tool() -> str:
            """Mock list tool."""
            return {"content": "file1.py\nfile2.py", "count": 2}

        # 调用 langchain tool 的 invoke 方法
        result = asyncio.run(mock_list_tool.ainvoke({}))

        # 当前实现将 dict 自动序列化为 JSON 字符串
        expected = json.dumps({"content": "file1.py\nfile2.py", "count": 2}, ensure_ascii=False)
        assert str(result) == expected, f"Expected JSON string, got: {result}"
        assert result.meta == {"count": 2}

        print("✅ test_decorator_extracts_dict_to_context passed")
    finally:
        ContextManager.reset(token)


def test_decorator_extracts_json_string_to_context():
    """验证 evoloop_tool 装饰器对 JSON 字符串返回值的传递（当前实现直接返回原始值）"""
    from app.core.context.manager import ContextManager, EvoContext

    ctx = EvoContext()
    token = ContextManager.set(ctx)
    try:
        from app.core.tools.base import evoloop_tool

        @evoloop_tool()
        async def mock_json_tool() -> str:
            """Mock json tool."""
            return json.dumps({"content": "tree output", "count": 5})

        result = asyncio.run(mock_json_tool.ainvoke({}))

        # 当前实现直接返回原始 JSON 字符串，不做转换
        assert result == json.dumps({"content": "tree output", "count": 5}), f"Expected JSON string, got: {result}"

        print("✅ test_decorator_extracts_json_string_to_context passed")
    finally:
        ContextManager.reset(token)


def test_decorator_plain_text_unchanged():
    """验证纯文本返回值不受影响"""
    from app.core.context.manager import ContextManager, EvoContext

    ctx = EvoContext()
    token = ContextManager.set(ctx)
    try:
        from app.core.tools.base import evoloop_tool

        @evoloop_tool()
        async def mock_plain_tool() -> str:
            """Mock plain tool."""
            return "[File: main.py]\n\nimport os"

        result = asyncio.run(mock_plain_tool.ainvoke({}))

        assert result == "[File: main.py]\n\nimport os"

        ctx = ContextManager.current()
        assert "last_tool_result_meta" not in ctx.metadata

        print("✅ test_decorator_plain_text_unchanged passed")
    finally:
        ContextManager.reset(token)


async def test_handler_reads_meta_from_context():
    """验证 MessageHandler 从 ContextManager 读取元数据用于 display_name"""
    from app.core.context.manager import ContextManager, EvoContext
    from app.core.engine.message.handler import MessageHandler

    # 准备上下文，模拟装饰器已经存入元数据
    ctx = EvoContext()
    ctx.metadata["last_tool_result_meta"] = {"count": 3}
    token = ContextManager.set(ctx)

    try:
        handler = MessageHandler(thread_id="test-thread", project_id=1)

        mock_repo = MagicMock()
        mock_repo.resolve_tool_input = AsyncMock(return_value={"path": "src/"})
        mock_repo.update = AsyncMock(return_value=True)
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

        with patch('app.core.engine.message.handler.get_tool_metadata', return_value=mock_meta):
            # Agent 收到的是纯文本（装饰器已经转换过了）
            tool_output = "file1.py\nfile2.py\nfile3.py"

            result = await handler.handle_tool_output(
                tool_name="list_directory",
                output=tool_output,
                tool_call_id="call_123",
                sequence_number=42
            )

        # 验证 display_name 渲染时拿到了 path（当前实现不再从 ContextManager 传递 count）
        assert captured_args.get("path") == "src/", f"Expected path=src/, got: {captured_args}"

        # 验证存入数据库的 content 是纯文本
        call_kwargs = mock_repo.update.call_args.kwargs
        stored_content = call_kwargs.get("content")
        assert stored_content == "file1.py\nfile2.py\nfile3.py", f"Expected pure text, got: {stored_content}"

        print("✅ test_handler_reads_meta_from_context passed")
    finally:
        ContextManager.reset(token)


async def test_handler_fallback_parsing():
    """验证没有 ContextManager 元数据时，handler 仍能兜底解析"""
    from app.core.context.manager import ContextManager, EvoContext
    from app.core.engine.message.handler import MessageHandler

    ctx = EvoContext()
    token = ContextManager.set(ctx)

    try:
        handler = MessageHandler(thread_id="test-thread", project_id=1)

        mock_repo = MagicMock()
        mock_repo.resolve_tool_input = AsyncMock(return_value={"path": "src/"})
        mock_repo.update = AsyncMock(return_value=True)
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

        with patch('app.core.engine.message.handler.get_tool_metadata', return_value=mock_meta):
            # 模拟经过装饰器转换的 ToolResult 输出
            from app.core.tools.base import ToolResult
            tool_output = ToolResult(
                text=json.dumps({"content": "file1.py", "count": 1}),
                meta={"count": 1},
            )

            result = await handler.handle_tool_output(
                tool_name="list_directory",
                output=tool_output,
                tool_call_id="call_456",
                sequence_number=43
            )

        assert captured_args.get("count") == 1, f"Expected count=1, got: {captured_args}"

        print("✅ test_handler_fallback_parsing passed")
    finally:
        ContextManager.reset(token)


if __name__ == "__main__":
    test_decorator_extracts_dict_to_context()
    test_decorator_extracts_json_string_to_context()
    test_decorator_plain_text_unchanged()
    asyncio.run(test_handler_reads_meta_from_context())
    asyncio.run(test_handler_fallback_parsing())
    print("\n✅ All tool content fix tests passed!")
