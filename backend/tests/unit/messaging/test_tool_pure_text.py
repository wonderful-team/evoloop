"""
测试工具返回纯文本，不再包装 JSON/dict
"""
import json
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import asyncio


async def test_list_dir_returns_plain_text():
    """验证 list_dir 返回纯文本"""
    from app.domain.tools.files.list_dir import handle_list

    # 在工作目录内创建测试目录，避免安全路径检查失败
    import os
    test_dir = os.path.join(os.getcwd(), "test_tmp_dir")
    os.makedirs(test_dir, exist_ok=True)
    try:
        open(os.path.join(test_dir, "file1.py"), "w").close()
        open(os.path.join(test_dir, "file2.py"), "w").close()

        # 使用相对路径
        result = await handle_list(path="test_tmp_dir", tree=False, stats=False)

        # handle_list 现在返回 tuple (text, meta)
        assert isinstance(result, tuple) and len(result) == 2, f"Expected tuple, got: {result}"
        text, meta = result
        assert isinstance(text, str)
        assert "file1.py" in text, f"Expected file1.py in result, got: {text}"
        assert "file2.py" in text
        assert not text.strip().startswith("{"), f"Should not be JSON, got: {text}"
        assert meta.get("count") == 2

        print("✅ test_list_dir_returns_plain_text passed")
    finally:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


async def test_list_dir_tree_returns_plain_text():
    """验证 list_dir 树形模式返回纯文本"""
    from app.domain.tools.files.list_dir import handle_list

    import os
    test_dir = os.path.join(os.getcwd(), "test_tmp_dir_tree")
    os.makedirs(os.path.join(test_dir, "sub"), exist_ok=True)
    try:
        open(os.path.join(test_dir, "sub", "file.py"), "w").close()

        result = await handle_list(path="test_tmp_dir_tree", tree=True, max_depth=2, stats=False)

        assert isinstance(result, tuple) and len(result) == 2
        text, meta = result
        assert isinstance(text, str)
        assert not text.strip().startswith("{"), f"Should not be JSON, got: {text}"

        print("✅ test_list_dir_tree_returns_plain_text passed")
    finally:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


async def test_grep_search_returns_plain_text():
    """验证 grep_search 返回纯文本"""
    from app.domain.tools.files.find_files import _search_by_name

    import os
    test_dir = os.path.join(os.getcwd(), "test_tmp_dir_search")
    os.makedirs(test_dir, exist_ok=True)
    try:
        open(os.path.join(test_dir, "test_file.py"), "w").close()

        result = await _search_by_name("test", test_dir, None, False, max_files=20)

        assert isinstance(result, tuple) and len(result) == 2
        text, meta = result
        assert isinstance(text, str)
        assert "test_file.py" in text
        assert not text.strip().startswith("{"), f"Should not be dict str, got: {text}"
        assert meta.get("count") == 1

        print("✅ test_grep_search_returns_plain_text passed")
    finally:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


async def test_display_name_without_count():
    """验证没有 count 时 display_name 仍能正常渲染（可选块消失）"""
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
        return f"已列出 {args.get('path')}"

    mock_meta.get_display_name = MagicMock(side_effect=capture_display_name)

    with patch('app.core.engine.message.handler._tool_mixin.get_tool_metadata', return_value=mock_meta):
        # 纯文本输出，没有 count
        tool_output = "file1.py\nfile2.py"

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

    print("✅ test_display_name_without_count passed")


if __name__ == "__main__":
    asyncio.run(test_list_dir_returns_plain_text())
    asyncio.run(test_list_dir_tree_returns_plain_text())
    asyncio.run(test_grep_search_returns_plain_text())
    asyncio.run(test_display_name_without_count())
    print("\n✅ All pure text tool tests passed!")
