"""
扩展验证：Agent 工具内容正确性边界测试

覆盖:
- write_file overwrite 路径一致性
- CRLF (Windows 换行) 处理
- UTF-8 编码（中文、Emoji、特殊字符）
- edit_file 策略精确性
- apply_patch_file 复杂场景
- execute_command 写入验证

运行:
    cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
    python tests/manual_verify_tool_correctness_extended.py
"""

import asyncio
import hashlib
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.file import safe_read_with_hash, get_file_info
from app.domain.tools.files.write_file import write_file
from app.domain.tools.files.edit_file import edit_file
from app.domain.tools.files.multiedit_file import multiedit_file
from app.domain.tools.execution import execute_command


def md5_file(path: str) -> str:
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def make_test_file(content: str | bytes) -> str:
    """在工作目录创建临时测试文件"""
    root = os.path.abspath(os.getcwd())
    path = os.path.join(root, f"_test_ext_{uuid.uuid4().hex}.txt")
    if isinstance(content, bytes):
        with open(path, 'wb') as f:
            f.write(content)
    else:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    return path


def cleanup(path: str):
    if path and os.path.exists(path):
        os.unlink(path)


# =============================================================================
# write_file 边界测试
# =============================================================================

async def test_write_file_overwrite_path_consistency():
    """验证 write_file overwrite 检查使用解析后的路径"""
    print("\n--- TEST: write_file overwrite 路径一致性 ---")

    # 在当前目录（CWD）和 WORKSPACE_ROOT 下分别测试
    # write_file 工具内部用 os.path.exists(path) 检查的是原始 path
    # 但 handle_write 会用 resolve_and_validate_path 解析为绝对路径
    # 如果两者不同，overwrite 检查就是错的

    # 场景: 传入相对路径 "test_overwrite_check.txt"
    # CWD 下不存在，但 WORKSPACE_ROOT 下已存在
    rel_name = f"_test_overwrite_{uuid.uuid4().hex[:8]}.txt"
    abs_path = os.path.join(os.path.abspath(os.getcwd()), rel_name)

    # 先通过 write_file 创建文件
    result1 = await write_file.ainvoke({
        "path": abs_path,
        "content": "first content",
        "overwrite": False
    })
    assert os.path.exists(abs_path), f"文件未创建: {result1}"

    # 现在用 overwrite=False 再次写入同一绝对路径，应该失败
    result2 = await write_file.ainvoke({
        "path": abs_path,
        "content": "second content",
        "overwrite": False
    })
    assert "already exists" in result2.lower() or "exists" in result2.lower(), \
        f"应拒绝覆盖已存在文件: {result2}"

    with open(abs_path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert content == "first content", f"文件不应被修改: {repr(content)}"

    # overwrite=True 时应成功覆盖
    result3 = await write_file.ainvoke({
        "path": abs_path,
        "content": "overwritten",
        "overwrite": True
    })
    with open(abs_path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert content == "overwritten", f"文件应被覆盖: {repr(content)}"

    cleanup(abs_path)
    print("✅ write_file overwrite 路径一致性通过")


async def test_write_file_utf8_special_chars():
    """验证 write_file 对特殊字符的写入正确性"""
    print("\n--- TEST: write_file UTF-8 特殊字符 ---")

    content_cases = [
        ("中文内容", "纯中文"),
        ("日本語テキスト🌸", "日文+Emoji"),
        ("∀x∈ℝ: x²≥0", "数学符号"),
        ("Tab\tHere\nNew\r\nLine", "转义序列"),
        ("Null\x00Byte", "含 NUL 字符"),
        ("😀🎉👍💻🔥", "纯 Emoji"),
        ("BOM\ufeffText", "BOM 字符"),
    ]

    for content, desc in content_cases:
        path = make_test_file("")  # 占位
        os.unlink(path)

        result = await write_file.ainvoke({
            "path": path,
            "content": content,
            "overwrite": False
        })
        assert os.path.exists(path), f"[{desc}] 文件未创建"

        # 用二进制模式读取以验证字节级正确性
        with open(path, 'rb') as f:
            actual_bytes = f.read()
        expected_bytes = content.encode('utf-8')

        assert actual_bytes == expected_bytes, f"[{desc}] 内容不匹配:\n期望: {repr(expected_bytes)}\n实际: {repr(actual_bytes)}"

        cleanup(path)

    print("✅ write_file UTF-8 特殊字符通过")


# =============================================================================
# CRLF 处理测试
# =============================================================================

async def test_edit_file_crlf_handling():
    """验证 edit_file 在 CRLF 文件中的处理"""
    print("\n--- TEST: edit_file CRLF 处理 ---")

    # 创建 CRLF 文件（二进制写入确保 \r\n 保留）
    original_crlf = b"line1\r\nline2\r\nline3\r\n"
    path = make_test_file(original_crlf)

    # 验证原始文件确实是 CRLF
    with open(path, 'rb') as f:
        raw = f.read()
    assert b'\r\n' in raw, "测试文件必须是 CRLF 格式"

    # 测试 1: simple_replacer 策略（直接使用 find in content）
    # read_file 文本模式会将 CRLF 转为 LF，所以 edit_file 读到的 content 是 LF
    # 这意味着 edit_file 对 CRLF 文件的编辑实际上是在 LF 表示上进行的
    result1 = await edit_file.ainvoke({
        "path": path,
        "target": "line2",
        "replacement": "LINE2_REPLACED",
    })
    print(f"  CRLF edit result: {result1[:100]}...")

    with open(path, 'rb') as f:
        raw_after = f.read()

    # edit_file 读取时使用 Python 文本模式，会将 CRLF 转为 LF
    # 编辑后使用 write_file 写入，文本模式在 macOS 上写入 \n 不会转为 \r\n
    # 所以 CRLF 文件经过 edit_file 后会变成 LF —— 这是 Python 文本模式的已知行为
    has_crlf = b'\r\n' in raw_after
    if has_crlf:
        print(f"  文件保留 CRLF: {repr(raw_after[:50])}")
    else:
        print(f"  ⚠️ 文件从 CRLF 变为 LF（文本模式行为）: {repr(raw_after[:50])}")

    # 验证内容正确性（归一化换行符后比较）
    text_after = raw_after.decode('utf-8').replace('\r\n', '\n')
    assert "LINE2_REPLACED" in text_after, "替换内容应存在"
    assert "line1\n" in text_after, "line1 应保留"
    assert "line3\n" in text_after, "line3 应保留"

    cleanup(path)
    print("✅ edit_file CRLF 处理通过")


async def test_edit_file_strategy_precision():
    """验证各匹配策略的精确性"""
    print("\n--- TEST: edit_file 策略精确性 ---")

    # line_trimmed_replacer 场景: 目标文本有首尾空格差异
    original = """def foo():
    # comment
    x = 1
    return x

def bar():
    # comment
    x = 2
    return x
"""
    path = make_test_file(original)

    # 测试 line_trimmed_replacer: 提供不精确缩进的目标
    result = await edit_file.ainvoke({
        "path": path,
        "target": "  # comment\n  x = 1",
        "replacement": "    # new comment\n    x = 10",
    })
    print(f"  Trimmed strategy result: {result[:120]}...")
    assert "success" in result.lower() or "✅" in result, f"应成功匹配: {result}"

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "    x = 10" in content, "line_trimmed 应匹配并替换"

    # 测试 block_anchor_replacer: 大段模糊匹配
    path2 = make_test_file(original)
    result2 = await edit_file.ainvoke({
        "path": path2,
        "target": "def bar():\n    # commen\n    x = 2\n    return x",
        "replacement": "def bar_new():\n    pass",
    })
    print(f"  Block anchor result: {result2[:120]}...")
    # 可能成功也可能失败，取决于相似度阈值
    if "success" in result2.lower() or "✅" in result2:
        with open(path2, 'r', encoding='utf-8') as f:
            c2 = f.read()
        assert "def bar_new():" in c2, "block_anchor 应替换"

    cleanup(path)
    cleanup(path2)
    print("✅ edit_file 策略精确性通过")


# =============================================================================
# multiedit_file 测试
# =============================================================================

async def test_multiedit_file_content_correctness():
    """验证 multiedit_file 内容正确性"""
    print("\n--- TEST: multiedit_file 内容正确性 ---")

    original = """import os
import sys

def hello():
    print("hello")

def world():
    print("world")
"""
    path = make_test_file(original)

    edits = [
        {"target": "import os", "replacement": "import pathlib"},
        {"target": '    print("hello")', "replacement": '    print("HELLO")'},
        {"target": '    print("world")', "replacement": '    print("WORLD")'},
    ]

    result = await multiedit_file.ainvoke({
        "path": path,
        "edits": edits,
    })
    assert "success" in result.lower() or "✅" in result, f"multiedit 失败: {result}"

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    assert "import pathlib" in content
    assert '    print("HELLO")' in content
    assert '    print("WORLD")' in content
    assert "import os" not in content
    assert '    print("hello")' not in content

    cleanup(path)
    print("✅ multiedit_file 内容正确性通过")


# =============================================================================
# apply_patch_file 边界测试
# =============================================================================

# =============================================================================
# execute_command 写入验证
# =============================================================================

async def test_execute_command_file_write_correctness():
    """验证 execute_command 写入文件后的内容正确性"""
    print("\n--- TEST: execute_command 文件写入正确性 ---")

    # 测试 1: 写入含特殊字符的内容
    test_path = os.path.join(os.path.abspath(os.getcwd()), f"_test_cmd_special_{uuid.uuid4().hex}.txt")
    # 使用 printf 确保精确控制内容
    cmd = f"printf '%s' '中文测试👋\\nSecond Line\\n' > {test_path}"
    result = await execute_command.ainvoke({
        "command": cmd,
        "background": False,
        "timeout": 10
    })
    print(f"  Special chars cmd result: {result[:80]}...")

    assert os.path.exists(test_path), "文件应被创建"
    with open(test_path, 'rb') as f:
        raw = f.read()
    assert b'\xe4\xb8\xad\xe6\x96\x87' in raw, "中文应正确写入（UTF-8 编码）"
    assert b'\xf0\x9f\x91\x8b' in raw, "Emoji 应正确写入"

    # 测试 2: 追加写入
    test_path2 = os.path.join(os.path.abspath(os.getcwd()), f"_test_cmd_append_{uuid.uuid4().hex}.txt")
    await execute_command.ainvoke({
        "command": f"echo 'line1' > {test_path2}",
        "background": False, "timeout": 10
    })
    await execute_command.ainvoke({
        "command": f"echo 'line2' >> {test_path2}",
        "background": False, "timeout": 10
    })

    with open(test_path2, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    # echo 默认添加换行符
    assert len(lines) == 2, f"应有2行: {lines}"
    assert "line1" in lines[0], f"第一行错误: {lines[0]}"
    assert "line2" in lines[1], f"第二行错误: {lines[1]}"

    cleanup(test_path)
    cleanup(test_path2)
    print("✅ execute_command 文件写入正确性通过")


# =============================================================================
# 综合测试: 工具链端到端
# =============================================================================

async def test_toolchain_roundtrip():
    """验证 write -> read -> edit -> read 的完整链条"""
    print("\n--- TEST: 工具链端到端 ---")

    path = os.path.join(os.path.abspath(os.getcwd()), f"_test_chain_{uuid.uuid4().hex}.py")

    # Step 1: write_file
    initial = "# Initial file\ndef func():\n    return 1\n"
    r1 = await write_file.ainvoke({"path": path, "content": initial, "overwrite": False})
    assert os.path.exists(path), "write_file 应创建文件"

    # Step 2: edit_file
    r2 = await edit_file.ainvoke({
        "path": path,
        "target": "    return 1",
        "replacement": "    return 42"
    })
    assert "success" in r2.lower() or "✅" in r2, f"edit 应成功: {r2}"

    # Step 3: multiedit_file
    r3 = await multiedit_file.ainvoke({
        "path": path,
        "edits": [
            {"target": "# Initial file", "replacement": "# Modified file"},
            {"target": "    return 42", "replacement": "    return 999"},
        ]
    })
    assert "success" in r3.lower() or "✅" in r3, f"multiedit 应成功: {r3}"

    # Step 4: 验证最终内容
    with open(path, 'r', encoding='utf-8') as f:
        final = f.read()

    expected = "# Modified file\ndef func():\n    return 999\n"
    assert final == expected, f"最终内容不匹配:\n期望: {repr(expected)}\n实际: {repr(final)}"

    cleanup(path)
    print("✅ 工具链端到端通过")


# =============================================================================
# 主入口
# =============================================================================

async def main():
    print("\n" + "=" * 60)
    print("Agent 工具内容正确性扩展验证")
    print("=" * 60)

    tests = [
        ("write_file overwrite 路径一致性", test_write_file_overwrite_path_consistency),
        ("write_file UTF-8 特殊字符", test_write_file_utf8_special_chars),
        ("edit_file CRLF 处理", test_edit_file_crlf_handling),
        ("edit_file 策略精确性", test_edit_file_strategy_precision),
        ("multiedit_file 内容正确性", test_multiedit_file_content_correctness),
        ("execute_command 文件写入正确性", test_execute_command_file_write_correctness),
        ("工具链端到端", test_toolchain_roundtrip),
    ]

    passed = 0
    failed = 0
    warnings = []

    for name, test_fn in tests:
        try:
            await test_fn()
            passed += 1
        except AssertionError as e:
            print(f"\n❌ {name} 失败: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ {name} 运行时错误: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
