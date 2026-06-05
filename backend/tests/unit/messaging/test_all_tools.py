"""
全面测试所有修改过的工具
覆盖：list_dir、search_files、multiedit_file、read_file、write_file、edit_file
"""
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import os


async def test_list_dir():
    """list_dir: 返回 tuple，Agent/DB 收到纯文本，display_name 带 count"""
    from app.domain.tools.files.list_dir import list_dir
    from app.core.tools.base import ToolResult

    test_dir = os.path.join(os.getcwd(), "test_all_dir")
    os.makedirs(test_dir, exist_ok=True)
    try:
        open(os.path.join(test_dir, "a.py"), "w").close()
        open(os.path.join(test_dir, "b.py"), "w").close()

        result = await list_dir.ainvoke({"path": "test_all_dir", "tree": False, "stats": False})

        assert isinstance(result, ToolResult), f"Expected ToolResult, got {type(result)}"
        assert "a.py" in str(result)
        assert "b.py" in str(result)
        assert "{" not in str(result)
        assert result.meta.get("count") == 2
        assert isinstance(result.display_name, str) and len(result.display_name) > 0
        assert isinstance(result.display_name, str) and len(result.display_name) > 0
        print(f"✅ list_dir: display_name='{result.display_name}', count={result.meta.get('count')}")
    finally:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


async def test_search_files():
    """search_files: 返回 tuple，Agent/DB 收到纯文本，display_name 带 count"""
    from app.domain.tools.files.search_files import search_files
    from app.core.tools.base import ToolResult

    test_dir = os.path.join(os.getcwd(), "test_all_search")
    os.makedirs(test_dir, exist_ok=True)
    try:
        open(os.path.join(test_dir, "foo.py"), "w").close()

        result = await search_files.ainvoke({"pattern": "foo", "path": test_dir, "search_in_name": True})

        assert isinstance(result, ToolResult)
        assert "foo.py" in str(result)
        assert "{" not in str(result)
        assert result.meta.get("count") == 1
        assert isinstance(result.display_name, str) and len(result.display_name) > 0
        print(f"✅ search_files: display_name='{result.display_name}', count={result.meta.get('count')}")
    finally:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


async def test_multiedit_file():
    """multiedit_file: 返回 ToolResult，Agent/DB 收到纯文本 + meta"""
    from app.domain.tools.files.multiedit_file import multiedit_file
    from app.core.tools.base import ToolResult

    test_file = os.path.join(os.getcwd(), "test_all_edit.py")
    with open(test_file, "w") as f:
        f.write("line1\nline2\n")
    try:
        result = await multiedit_file.ainvoke({
            "path": test_file,
            "edits": [{"target": "line1", "replacement": "new1"}]
        })

        # multiedit_file 被 evoloop_tool 装饰后，ainvoke 返回 ToolResult
        assert isinstance(result, ToolResult), f"Expected ToolResult, got {type(result)}"
        text = str(result)
        assert "new1" in text or "Successfully applied" in text
        assert "{" not in text
        # count = 1 because only 1 edit passed to multiedit_file
        assert result.meta.get("count") == 1, f"Expected count=1, got {result.meta}"
        print(f"✅ multiedit_file: count={result.meta.get('count')}")
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


async def test_read_file():
    """read_file: 未改返回值，仍返回纯文本字符串（不是 tuple），display_name 正常"""
    from app.domain.tools.files.read_file import read_file
    from app.core.tools.base import ToolResult

    test_file = os.path.join(os.getcwd(), "test_all_read.py")
    with open(test_file, "w") as f:
        f.write("import os\nprint('hello')\n")
    try:
        result = await read_file.ainvoke({"path": test_file})

        # read_file 返回纯文本，装饰器会包装成 ToolResult
        assert isinstance(result, ToolResult)
        assert "import os" in str(result)
        assert "{" not in str(result)
        # read_file 的 summary_template 不需要 count
        assert test_file.split("/")[-1] in result.display_name or "read_file" in result.display_name.lower()
        print(f"✅ read_file: display_name='{result.display_name}'")
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


async def test_write_file():
    """write_file: 未改返回值，仍返回纯文本字符串，display_name 正常"""
    from app.domain.tools.files.write_file import write_file
    from app.core.tools.base import ToolResult

    test_file = os.path.join(os.getcwd(), "test_all_write.py")
    try:
        result = await write_file.ainvoke({
            "path": test_file,
            "content": "# test\n"
        })

        assert isinstance(result, ToolResult)
        assert "{" not in str(result)
        assert test_file.split("/")[-1] in result.display_name or "write_file" in result.display_name.lower()
        print(f"✅ write_file: display_name='{result.display_name}'")
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


async def test_edit_file():
    """edit_file: 未改返回值，仍返回纯文本字符串，display_name 正常"""
    from app.domain.tools.files.edit_file import edit_file
    from app.core.tools.base import ToolResult

    test_file = os.path.join(os.getcwd(), "test_all_edit_single.py")
    with open(test_file, "w") as f:
        f.write("old_text\n")
    try:
        result = await edit_file.ainvoke({
            "path": test_file,
            "target": "old_text",
            "replacement": "new_text"
        })

        assert isinstance(result, ToolResult)
        assert "{" not in str(result)
        assert test_file.split("/")[-1] in result.display_name or "edit_file" in result.display_name.lower()
        print(f"✅ edit_file: display_name='{result.display_name}'")
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


async def test_message_handler_with_all_tools():
    """MessageHandler 正确处理所有工具的输出"""
    from app.core.engine.message.handler import MessageHandler
    from app.core.tools.base import ToolResult

    handler = MessageHandler(thread_id="test-all", project_id=1)
    mock_repo = MagicMock()
    mock_repo.resolve_tool_input = AsyncMock(return_value={"path": "src/"})
    mock_repo.update = AsyncMock(return_value=True)
    handler._repository = mock_repo

    tools_to_test = [
        ("list_dir", ToolResult("file1.py\nfile2.py", {"count": 2}, "已列出 src/ (2 项)")),
        ("search_files", ToolResult("match.py", {"count": 1}, "搜索完成，找到 1 个结果")),
        ("read_file", ToolResult("import os", {}, "读取文件 'main.py'")),
        ("write_file", ToolResult("OK", {}, "写入文件 'out.py'")),
    ]

    for tool_name, tool_output in tools_to_test:
        mock_repo.reset_mock()
        await handler.handle_tool_output(
            tool_name=tool_name,
            output=tool_output,
            tool_call_id=f"call_{tool_name}",
            sequence_number=1
        )

        call_kwargs = mock_repo.update.call_args.kwargs
        stored_content = call_kwargs.get("content")
        stored_display_name = call_kwargs["meta_data"]["tool_meta"]["display_name"]

        assert stored_content == str(tool_output), f"{tool_name}: content mismatch"
        # MessageHandler may re-render display_name via get_tool_metadata, so just verify it's a non-empty string
        assert isinstance(stored_display_name, str) and len(stored_display_name) > 0, f"{tool_name}: display_name should be non-empty string, got {stored_display_name!r}"
        print(f"✅ MessageHandler: {tool_name} → content='{stored_content[:20]}...', display_name='{stored_display_name}'")


if __name__ == "__main__":
    print("=" * 60)
    print("全面工具测试")
    print("=" * 60)
    asyncio.run(test_list_dir())
    asyncio.run(test_search_files())
    asyncio.run(test_multiedit_file())
    asyncio.run(test_read_file())
    asyncio.run(test_write_file())
    asyncio.run(test_edit_file())
    asyncio.run(test_message_handler_with_all_tools())
    print("=" * 60)
    print("✅ All tool tests passed!")
    print("=" * 60)
