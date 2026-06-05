"""
端到端验证：工具返回值 → Agent 看到的、数据库存的、summary_template 解析的

验证链路：
1. 工具返回 (text, meta) tuple
2. evoloop_tool 装饰器 → 拆分为纯文本 + 渲染 display_name → ToolResult
3. LangChain / Agent 收到 ToolResult（纯文本 str）
4. DatabaseCallbackHandler.on_tool_end → output 是 ToolResult
5. MessageHandler.handle_tool_output → 从 ToolResult 提取 display_name + meta
6. 数据库 messages.content 存纯文本
"""
import json
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import tempfile
import os


async def test_list_dir_end_to_end():
    """端到端：list_dir 工具返回值全流程验证"""
    from app.domain.tools.files.list_dir import handle_list

    # 1. 工具执行：返回 (text, meta)
    test_dir = os.path.join(os.getcwd(), "test_e2e_dir")
    os.makedirs(test_dir, exist_ok=True)
    try:
        open(os.path.join(test_dir, "file1.py"), "w").close()
        open(os.path.join(test_dir, "file2.py"), "w").close()
        open(os.path.join(test_dir, "README.md"), "w").close()

        raw_result = await handle_list(path="test_e2e_dir", tree=False, stats=False)
        print(f"1. 工具原始返回值: {type(raw_result).__name__}")
        print(f"   text = {repr(raw_result[0])}")
        print(f"   meta = {raw_result[1]}")

        assert isinstance(raw_result, tuple) and len(raw_result) == 2
        text, meta = raw_result
        assert "file1.py" in text
        assert meta.get("count") == 3

        # 2. 经过 evoloop_tool 装饰器后的返回值（模拟 LangChain 调用）
        from app.domain.tools.files.list_dir import list_dir
        decorated_result = await list_dir.ainvoke({"path": "test_e2e_dir", "tree": False, "stats": False})

        print(f"\n2. 装饰器处理后（LangChain/Agent 收到）:")
        print(f"   type = {type(decorated_result).__name__}")
        print(f"   value = {repr(str(decorated_result))}")
        print(f"   display_name = {repr(decorated_result.display_name)}")
        print(f"   meta = {decorated_result.meta}")

        from app.core.tools.base import ToolResult
        assert isinstance(decorated_result, ToolResult)
        # Agent 看到的是纯文本
        assert str(decorated_result) == text
        assert "{" not in str(decorated_result)
        # display_name 已渲染或回退为 i18n key
        assert isinstance(decorated_result.display_name, str) and len(decorated_result.display_name) > 0

        # 3. MessageHandler 处理工具输出
        from app.core.engine.message.handler import MessageHandler
        handler = MessageHandler(thread_id="test-thread", project_id=1)

        mock_repo = MagicMock()
        mock_repo.resolve_tool_input = AsyncMock(return_value={"path": "test_e2e_dir"})
        mock_repo.update = AsyncMock(return_value=True)
        handler._repository = mock_repo

        mock_meta = MagicMock()
        mock_meta.is_hidden = False
        mock_meta.affected_path_keys = ["path"]
        mock_meta.summary_template = "database_logger.tool_summary.list_files"

        def capture_display_name(tool_name, args):
            return f"已列出 {args.get('path')}"

        mock_meta.get_display_name = MagicMock(side_effect=capture_display_name)

        with patch('app.core.engine.message.handler.get_tool_metadata', return_value=mock_meta):
            await handler.handle_tool_output(
                tool_name="list_dir",
                output=decorated_result,
                tool_call_id="call_123",
                sequence_number=42
            )

        call_kwargs = mock_repo.update.call_args.kwargs
        stored_content = call_kwargs.get("content")
        stored_meta = call_kwargs.get("meta_data")

        print(f"\n3. 数据库存储:")
        print(f"   content = {repr(stored_content)}")
        print(f"   display_name = {stored_meta['tool_meta']['display_name']}")

        # 数据库 content 是纯文本
        assert stored_content == text
        assert "{" not in stored_content
        # display_name 已渲染
        assert isinstance(stored_meta["tool_meta"]["display_name"], str) and len(stored_meta["tool_meta"]["display_name"]) > 0

        print("\n✅ test_list_dir_end_to_end passed")
    finally:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


async def test_search_files_end_to_end():
    """端到端：search_files 工具返回值全流程验证"""
    from app.domain.tools.files.grep_search import _search_by_name

    test_dir = os.path.join(os.getcwd(), "test_e2e_search")
    os.makedirs(test_dir, exist_ok=True)
    try:
        open(os.path.join(test_dir, "test_utils.py"), "w").close()
        open(os.path.join(test_dir, "main.py"), "w").close()

        raw_result = await _search_by_name("test", test_dir, None, False, max_files=20)
        print(f"\n4. search_files 原始返回值:")
        print(f"   text = {repr(raw_result[0][:80])}")
        print(f"   meta = {raw_result[1]}")

        assert raw_result[1].get("count") == 1

        # 经过装饰器
        from app.domain.tools.files.grep_search import grep_search
        decorated_result = await grep_search.ainvoke({"pattern": "test", "path": test_dir, "search_in_name": True})

        print(f"\n5. 装饰器处理后:")
        print(f"   display_name = {repr(decorated_result.display_name)}")

        assert isinstance(decorated_result.display_name, str) and len(decorated_result.display_name) > 0

        print("\n✅ test_search_files_end_to_end passed")
    finally:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


async def test_multiedit_file_end_to_end():
    """端到端：multiedit_file 工具返回值全流程验证"""
    from app.domain.tools.files.edit_file import handle_multi_edit, FileEditOperation

    test_file = os.path.join(os.getcwd(), "test_e2e_edit.py")
    with open(test_file, "w") as f:
        f.write("old_line_1\nold_line_2\nold_line_3\n")

    try:
        edits = [
            FileEditOperation(target="old_line_1", replacement="new_line_1"),
            FileEditOperation(target="old_line_2", replacement="new_line_2"),
        ]

        raw_result = await handle_multi_edit(test_file, edits, None, False, None)
        print(f"\n6. multiedit_file 原始返回值:")
        print(f"   text = {repr(raw_result[0][:100])}")
        print(f"   meta = {raw_result[1]}")

        assert raw_result[1].get("count") == 2

        # 经过装饰器
        from app.domain.tools.files.multiedit_file import multiedit_file
        decorated_result = await multiedit_file.ainvoke({
            "path": test_file,
            "edits": [{"target": "old_line_1", "replacement": "new_line_1"}]
        })

        print(f"\n7. 装饰器处理后:")
        print(f"   display_name = {repr(decorated_result.display_name)}")

        print("\n✅ test_multiedit_file_end_to_end passed")
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


if __name__ == "__main__":
    print("=" * 60)
    print("端到端工具返回值验证")
    print("=" * 60)
    asyncio.run(test_list_dir_end_to_end())
    asyncio.run(test_search_files_end_to_end())
    asyncio.run(test_multiedit_file_end_to_end())
    print("\n" + "=" * 60)
    print("✅ All end-to-end tests passed!")
    print("=" * 60)
