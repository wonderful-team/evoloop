"""
测试工具 JSON 输出中的 content 提取逻辑

验证：list_dir 返回的 json.dumps({"content": ..., "count": ...})
在存入 messages 表前，content 字段应被提取为纯文本，
而 count 等元数据仍保留在 result_meta 中供 display_name 使用。
"""
import json
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')


def test_extract_content_from_json_tool_output():
    """模拟 MessageHandler.handle_tool_output 中的 JSON content 提取逻辑"""

    # 模拟 list_dir 的返回值
    tool_output = json.dumps({
        "content": "file1.py\nfile2.py\nREADME.md",
        "count": 3
    })

    # 原始逻辑：content = str(output)
    content = str(tool_output) if tool_output else ""

    # 新增逻辑：提取 JSON 中的真实 content
    if content.strip().startswith("{"):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "content" in parsed:
                content = parsed["content"]
        except (ValueError, Exception):
            pass

    # 断言：content 应该是纯文本，不是 JSON 串
    assert content == "file1.py\nfile2.py\nREADME.md", f"Expected pure text, got: {content}"
    assert "{" not in content, "content should not contain JSON braces"

    # 断言：result_meta 仍然可以从原始 output 解析得到
    result_meta = {}
    output_str = str(tool_output)
    if output_str.strip().startswith("{"):
        try:
            parsed = json.loads(output_str)
            if isinstance(parsed, dict):
                result_meta = {k.lower(): v for k, v in parsed.items()}
        except (ValueError, Exception):
            pass

    assert result_meta.get("count") == 3, f"Expected count=3, got: {result_meta}"

    print("✅ test_extract_content_from_json_tool_output passed")


def test_plain_text_tool_output_unchanged():
    """纯文本工具输出（如 read_file）不应受影响"""

    tool_output = "[File: main.py | Lines 1-10 of 50 | Hash: abc123]\n\nimport os\n"

    content = str(tool_output) if tool_output else ""

    if content.strip().startswith("{"):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "content" in parsed:
                content = parsed["content"]
        except (ValueError, Exception):
            pass

    assert content == tool_output, "Plain text output should remain unchanged"
    print("✅ test_plain_text_tool_output_unchanged passed")


def test_tree_mode_json_output():
    """树形模式下的 JSON 输出也应正确提取"""

    tree_output = "src/\n  core/\n    engine.py\n  utils.py\n"
    tool_output = json.dumps({"content": tree_output, "count": 4})

    content = str(tool_output) if tool_output else ""

    if content.strip().startswith("{"):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "content" in parsed:
                content = parsed["content"]
        except (ValueError, Exception):
            pass

    assert content == tree_output
    assert "src/" in content
    assert "{" not in content
    print("✅ test_tree_mode_json_output passed")


def test_invalid_json_fallback():
    """非 JSON 内容不应被错误处理"""

    tool_output = "Error: Permission denied for /etc/shadow"

    content = str(tool_output) if tool_output else ""

    if content.strip().startswith("{"):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "content" in parsed:
                content = parsed["content"]
        except (ValueError, Exception):
            pass

    assert content == tool_output
    print("✅ test_invalid_json_fallback passed")


def test_json_without_content_key():
    """JSON 中没有 content 键时不应提取"""

    tool_output = json.dumps({"status": "ok", "items": [1, 2, 3]})

    content = str(tool_output) if tool_output else ""

    if content.strip().startswith("{"):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "content" in parsed:
                content = parsed["content"]
        except (ValueError, Exception):
            pass

    # 因为没有 "content" 键，所以保持原样
    assert content == tool_output
    print("✅ test_json_without_content_key passed")


def test_python_dict_with_content():
    """Python dict 类型的工具输出（如 grep_search）也应正确提取"""

    tool_output = {"content": "match1.py:10\nmatch2.py:20", "count": 2}

    # 模拟 handler.py 中的修复逻辑
    content = str(tool_output) if tool_output else ""

    if isinstance(tool_output, dict) and "content" in tool_output:
        content = tool_output["content"]
    elif content.strip().startswith("{"):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "content" in parsed:
                content = parsed["content"]
        except (ValueError, Exception):
            pass

    assert content == "match1.py:10\nmatch2.py:20", f"Expected pure text, got: {content}"
    assert "{" not in content
    print("✅ test_python_dict_with_content passed")


def test_python_dict_without_content_key():
    """Python dict 没有 content 键时不应提取"""

    tool_output = {"result_type": "success", "data": [1, 2, 3]}

    content = str(tool_output) if tool_output else ""

    if isinstance(tool_output, dict) and "content" in tool_output:
        content = tool_output["content"]
    elif content.strip().startswith("{"):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "content" in parsed:
                content = parsed["content"]
        except (ValueError, Exception):
            pass

    assert content == str(tool_output)
    print("✅ test_python_dict_without_content_key passed")


if __name__ == "__main__":
    test_extract_content_from_json_tool_output()
    test_plain_text_tool_output_unchanged()
    test_tree_mode_json_output()
    test_invalid_json_fallback()
    test_json_without_content_key()
    test_python_dict_with_content()
    test_python_dict_without_content_key()
    print("\n✅ All tool JSON content extract tests passed!")
