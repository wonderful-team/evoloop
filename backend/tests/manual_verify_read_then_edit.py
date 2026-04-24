"""
先读后改链路验证 — read_file → edit_file 内容一致性

验证核心假设:
1. read_file 返回的内容和 edit_file 内部读取的内容一致
2. LLM 基于 read_file 输出构造的 target 能被 edit_file 正确匹配
3. 各种编码/换行符场景下链路仍然正确

运行:
    cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
    python tests/manual_verify_read_then_edit.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.tools.files.read_file import read_file
from app.domain.tools.files.edit_file import edit_file


def make_test_file(content: str | bytes) -> str:
    root = os.path.abspath(os.getcwd())
    path = os.path.join(root, f"_test_rte_{os.urandom(4).hex()}.txt")
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


def extract_content_from_read_output(output: str) -> str:
    """从 read_file 的输出中提取实际文件内容（去掉 metadata 前缀）"""
    lines = output.split('\n')
    # 找到第一个非空行且不是 [File: ...] 的行
    start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('[File:') or line.startswith('[Large File:'):
            start_idx = i + 1
            break
    # 跳过可能的 [Use start_line=...] 提示
    while start_idx < len(lines) and lines[start_idx].startswith('[Use start_line='):
        start_idx += 1
    # 跳过可能的空行
    while start_idx < len(lines) and lines[start_idx].strip() == '':
        start_idx += 1
    return '\n'.join(lines[start_idx:])


async def test_read_then_edit_basic():
    """基础场景：先读后改"""
    print("\n--- TEST: 先读后改（基础） ---")

    original = "def hello():\n    return 1\n\ndef world():\n    return 2\n"
    path = make_test_file(original)

    # Step 1: read_file
    read_result = await read_file.ainvoke({"path": path})
    print(f"  Read output preview: {read_result[:80]}...")

    # Step 2: 从 read 输出提取内容，构造 edit target
    content = extract_content_from_read_output(read_result)
    assert "def hello():" in content, "read_file 应返回文件内容"

    # LLM 通常会看到内容后构造 edit
    target = "    return 1"
    replacement = "    return 100"

    # Step 3: edit_file
    edit_result = await edit_file.ainvoke({
        "path": path,
        "target": target,
        "replacement": replacement,
    })
    print(f"  Edit result: {edit_result[:80]}...")
    assert "success" in edit_result.lower() or "✅" in edit_result, f"编辑应成功: {edit_result}"

    # Step 4: 再次读取验证
    read_after = await read_file.ainvoke({"path": path})
    content_after = extract_content_from_read_output(read_after)
    assert "    return 100" in content_after, "修改应生效"
    assert "    return 1\n" not in content_after, "旧内容应被替换"
    assert "def world():" in content_after, "无关内容应保留"

    cleanup(path)
    print("✅ 先读后改（基础）通过")


async def test_read_then_edit_chinese():
    """中文场景：先读后改"""
    print("\n--- TEST: 先读后改（中文内容） ---")

    original = "# 测试文件\ndef  greet():\n    return '你好'\n\ndef  farewell():\n    return '再见'\n"
    path = make_test_file(original)

    read_result = await read_file.ainvoke({"path": path})
    content = extract_content_from_read_output(read_result)
    assert "你好" in content, "read_file 应正确读取中文"

    edit_result = await edit_file.ainvoke({
        "path": path,
        "target": "    return '你好'",
        "replacement": "    return '你好，世界！👋'",
    })
    assert "success" in edit_result.lower() or "✅" in edit_result, f"中文编辑应成功: {edit_result}"

    read_after = await read_file.ainvoke({"path": path})
    content_after = extract_content_from_read_output(read_after)
    assert "你好，世界！👋" in content_after, "中文+Emoji 修改应生效"

    cleanup(path)
    print("✅ 先读后改（中文内容）通过")


async def test_read_then_edit_crlf():
    """CRLF 场景：先读后改"""
    print("\n--- TEST: 先读后改（CRLF 文件） ---")

    # 创建 CRLF 文件
    original_crlf = b"line1\r\nline2\r\nline3\r\nline4\r\n"
    path = make_test_file(original_crlf)

    # 验证原始文件确实是 CRLF
    with open(path, 'rb') as f:
        raw = f.read()
    assert b'\r\n' in raw, "测试文件必须是 CRLF"

    # Step 1: read_file（文本模式会将 CRLF 转为 LF）
    read_result = await read_file.ainvoke({"path": path})
    content = extract_content_from_read_output(read_result)

    # read_file 返回的内容中换行符是 \n（因为文本模式转换）
    assert "line2" in content, "应能读取到 line2"
    assert '\r' not in content, "read_file 输出不应含 \\r"

    # Step 2: edit_file（同样使用文本模式，读取的也是 LF 版本）
    edit_result = await edit_file.ainvoke({
        "path": path,
        "target": "line2",
        "replacement": "LINE2_MODIFIED",
    })
    print(f"  Edit result: {edit_result[:80]}...")
    assert "success" in edit_result.lower() or "✅" in edit_result, f"CRLF 编辑应成功: {edit_result}"

    # Step 3: 验证（文件现在是 LF）
    read_after = await read_file.ainvoke({"path": path})
    content_after = extract_content_from_read_output(read_after)
    assert "LINE2_MODIFIED" in content_after, "CRLF→LF 后编辑应生效"
    assert "line1" in content_after, "line1 应保留"
    assert "line3" in content_after, "line3 应保留"

    cleanup(path)
    print("✅ 先读后改（CRLF 文件）通过")


async def test_read_then_multiedit():
    """先读后批量改"""
    print("\n--- TEST: 先读后批量改 ---")

    original = """import os
import sys

def hello():
    print("hello")

def world():
    print("world")
"""
    path = make_test_file(original)

    read_result = await read_file.ainvoke({"path": path})
    content = extract_content_from_read_output(read_result)
    assert "import os" in content, "应读取到 import os"

    edits = [
        {"target": "import os", "replacement": "import pathlib"},
        {"target": '    print("hello")', "replacement": '    print("HELLO")'},
        {"target": '    print("world")', "replacement": '    print("WORLD")'},
    ]

    edit_result = await edit_file.ainvoke({"path": path, "edits": edits})
    assert "success" in edit_result.lower() or "✅" in edit_result, f"批量编辑应成功: {edit_result}"

    read_after = await read_file.ainvoke({"path": path})
    content_after = extract_content_from_read_output(read_after)
    assert "import pathlib" in content_after
    assert '    print("HELLO")' in content_after
    assert '    print("WORLD")' in content_after
    assert "import os" not in content_after

    cleanup(path)
    print("✅ 先读后批量改通过")


async def test_read_then_edit_hash_verification():
    """先读后带 hash 验证的编辑"""
    print("\n--- TEST: 先读后带 hash 验证编辑 ---")

    original = "# Step 1\nx = 1\n# Step 2\ny = 2\n"
    path = make_test_file(original)

    # 第一次读取获取 hash
    read_result = await read_file.ainvoke({"path": path})
    # 从输出中提取 hash（格式: [File: path | Lines X-Y of N | Hash: abc123...]）
    hash_val = None
    for line in read_result.split('\n'):
        if 'Hash:' in line:
            # 格式示例: [File: path | Lines 1-4 of 4 | Hash: 185cefb03358b161]
            hash_start = line.find('Hash:') + len('Hash:')
            hash_end = line.find(']', hash_start)
            if hash_end == -1:
                hash_end = len(line)
            hash_val = line[hash_start:hash_end].strip()
            break

    assert hash_val, f"应从 read_file 输出中提取到 hash，输出: {read_result[:100]}"
    print(f"  Extracted hash: {hash_val}")

    # 使用 hash 进行编辑（乐观锁）
    edit_result = await edit_file.ainvoke({
        "path": path,
        "target": "x = 1",
        "replacement": "x = 100",
        "expected_hash": hash_val,
    })
    assert "success" in edit_result.lower() or "✅" in edit_result, f"带 hash 编辑应成功: {edit_result}"

    # 验证内容
    read_after = await read_file.ainvoke({"path": path})
    content_after = extract_content_from_read_output(read_after)
    assert "x = 100" in content_after, "hash 验证编辑应生效"

    # 再次用旧 hash 编辑应失败（文件已修改）
    edit_result2 = await edit_file.ainvoke({
        "path": path,
        "target": "y = 2",
        "replacement": "y = 200",
        "expected_hash": hash_val,
    })
    assert "hash" in edit_result2.lower() or "modified" in edit_result2.lower(), f"旧 hash 应被拒绝: {edit_result2}"
    print(f"  旧 hash 拒绝: {edit_result2[:60]}...")

    cleanup(path)
    print("✅ 先读后带 hash 验证编辑通过")


async def main():
    print("\n" + "=" * 60)
    print("先读后改链路验证")
    print("=" * 60)

    tests = [
        ("先读后改（基础）", test_read_then_edit_basic),
        ("先读后改（中文内容）", test_read_then_edit_chinese),
        ("先读后改（CRLF 文件）", test_read_then_edit_crlf),
        ("先读后批量改", test_read_then_multiedit),
        ("先读后带 hash 验证编辑", test_read_then_edit_hash_verification),
    ]

    passed = 0
    failed = 0

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
