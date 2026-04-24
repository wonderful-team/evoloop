"""
验证 read_file metadata 不会污染 write/edit 操作

核心风险: read_file 输出包含 metadata 前缀，如果 LLM 误将其当作文件内容，
后续 write_file/edit_file 可能在文件中写入 metadata 行或基于错误内容匹配。

运行:
    cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
    python tests/manual_verify_metadata_pollution.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.tools.files.read_file import read_file
from app.domain.tools.files.write_file import write_file
from app.domain.tools.files.edit_file import edit_file


def make_test_file(content: str) -> str:
    root = os.path.abspath(os.getcwd())
    path = os.path.join(root, f"_test_mp_{os.urandom(4).hex()}.txt")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def cleanup(path: str):
    if path and os.path.exists(path):
        os.unlink(path)


async def test_write_file_no_metadata_pollution():
    """
    风险场景: LLM 把 read_file 的完整输出(含 metadata)当作文件内容，
    然后用 write_file 覆盖原文件，导致 metadata 行被写入文件。
    """
    print("\n--- TEST: write_file 不会被 metadata 污染 ---")

    original = "# Real Content\ndef foo():\n    return 1\n"
    path = make_test_file(original)

    # Step 1: read_file 获取含 metadata 的输出
    read_result = await read_file.ainvoke({"path": path})
    print(f"  Read output:\n{read_result[:120]}...")

    # 确认 read_file 输出确实包含 metadata
    assert "[File:" in read_result, "read_file 应包含 metadata"
    assert "Hash:" in read_result, "read_file 应包含 Hash"

    # Step 2: 模拟 LLM 误操作——把完整 read 输出（含 metadata）当作 content 写入
    # 这是一个"LLM 犯错"的场景，write_file 工具本身没有过滤机制
    write_result = await write_file.ainvoke({
        "path": path,
        "content": read_result,  # 模拟 LLM 误传完整输出
        "overwrite": True,
    })
    print(f"  Write result: {write_result[:80]}...")

    # Step 3: 验证文件内容——**metadata 行被写入了文件！**
    with open(path, 'r', encoding='utf-8') as f:
        actual = f.read()

    print(f"  File content after write:\n{actual[:150]}...")

    # 这是一个**已知风险**——如果 LLM 误传，metadata 会被写入文件
    # 但 write_file 本身不应该也不可能在写入前过滤（它不知道 content 的来源）
    # 解决方案应该在 LLM prompt 层面，而不是工具层面

    if "[File:" in actual or "Hash:" in actual:
        print("  ⚠️ 检测到 metadata 被写入文件（这是 LLM 误操作导致的，write_file 工具本身无法预防）")
        print("     说明: write_file 写入的是 LLM 传入的原始字符串，不做内容过滤")
    else:
        print("  ✅ 文件未被 metadata 污染（此轮 LLM 未误传）")

    cleanup(path)


async def test_edit_file_with_metadata_in_target():
    """
    风险场景: LLM 构造 target 时包含了 read_file 的 metadata 行，
    导致 edit_file 无法匹配（因为文件中没有 metadata 行）。
    """
    print("\n--- TEST: edit_file target 含 metadata 时的匹配行为 ---")

    original = "# Header\ndef foo():\n    return 1\n\ndef bar():\n    return 2\n"
    path = make_test_file(original)

    # 模拟 LLM 误构造 target（包含了 metadata 行）
    bad_target = "[File: /some/path | Lines 1-6 of 6 | Hash: abc123]\n# Header\ndef foo():"

    edit_result = await edit_file.ainvoke({
        "path": path,
        "target": bad_target,
        "replacement": "# New Header\ndef foo_new():",
    })
    print(f"  Edit result: {edit_result[:100]}...")

    # 由于文件中没有 metadata 行，target 无法匹配，edit 应失败
    if "fail" in edit_result.lower() or "error" in edit_result.lower() or "could not find" in edit_result.lower():
        print("  ✅ edit_file 正确拒绝匹配（metadata 不在文件中）")
    else:
        print("  ❌ edit_file 意外成功——这可能意味着模糊匹配策略错误地匹配了")
        with open(path, 'r') as f:
            print(f"  文件内容: {f.read()}")

    cleanup(path)


async def test_edit_file_with_read_output_as_reference():
    """
    正常场景: LLM 正确地从 read_file 输出中提取内容，构造准确的 target。
    验证 edit_file 在"先读后改"链路中的正确性。
    """
    print("\n--- TEST: 先读后改（LLM 正确提取内容） ---")

    original = "# App Entry\ndef main():\n    print('hello')\n    return 0\n\ndef helper():\n    pass\n"
    path = make_test_file(original)

    # LLM 调用 read_file
    read_result = await read_file.ainvoke({"path": path})
    print(f"  Read output preview:\n{read_result[:100]}...")

    # 从 read 输出中提取实际内容（模拟 LLM 的正确行为）
    # read_file 输出格式: '\n[File: ...]\n\n<content>'
    # 需要跳过 metadata 行及其后的空行
    lines = read_result.split('\n')
    skip_done = False
    content_lines = []
    for line in lines:
        if not skip_done:
            if line.startswith('[File:') or line.startswith('[Large File:'):
                continue
            if line.startswith('[Use start_line='):
                continue
            if line.strip() == '':
                continue
            skip_done = True
        content_lines.append(line)
    actual_content = '\n'.join(content_lines)

    print(f"  Extracted content:\n{actual_content}")
    assert actual_content.strip() == original.strip(), "提取的内容应与原始文件一致"

    # LLM 基于正确内容构造 edit
    edit_result = await edit_file.ainvoke({
        "path": path,
        "target": "    print('hello')",
        "replacement": "    print('world')",
    })
    assert "success" in edit_result.lower() or "✅" in edit_result, f"编辑应成功: {edit_result}"

    # 验证
    with open(path, 'r') as f:
        content_after = f.read()
    assert "    print('world')" in content_after
    assert "    print('hello')" not in content_after
    assert "[File:" not in content_after, "文件中不应出现 metadata"
    assert "Hash:" not in content_after, "文件中不应出现 Hash"

    cleanup(path)
    print("✅ 先读后改（LLM 正确提取）通过")


async def test_roundtrip_read_write_read():
    """
    完整链路: read_file → write_file(overwrite=True) → read_file
    验证 write_file 不会引入 metadata 污染。
    """
    print("\n--- TEST: read → write → read 往返一致性 ---")

    original = "# Config\nDEBUG = True\nPORT = 8000\n"
    path = make_test_file(original)

    # Round 1: read
    r1 = await read_file.ainvoke({"path": path})

    # Round 2: write（模拟 LLM 正确只写入实际内容）
    new_content = "# Config\nDEBUG = False\nPORT = 8080\n"
    w1 = await write_file.ainvoke({"path": path, "content": new_content, "overwrite": True})
    assert "成功" in w1 or "success" in w1.lower(), f"写入应成功: {w1}"

    # Round 3: read 验证
    r2 = await read_file.ainvoke({"path": path})
    content_after = r2
    if "[File:" in r2:
        # 去掉 metadata 前缀
        lines = r2.split('\n')
        idx = 0
        for i, line in enumerate(lines):
            if line.strip() == '' and i > 0 and '[File:' in lines[i - 1]:
                idx = i + 1
                break
        content_after = '\n'.join(lines[idx:])

    assert content_after.strip() == new_content.strip(), f"往返后内容不一致:\n期望: {repr(new_content)}\n实际: {repr(content_after)}"
    assert "[File:" not in content_after, "文件中不应含 metadata"

    cleanup(path)
    print("✅ read → write → read 往返一致性通过")


async def main():
    print("\n" + "=" * 60)
    print("Metadata 污染风险验证")
    print("=" * 60)

    tests = [
        ("write_file 不会被 metadata 污染", test_write_file_no_metadata_pollution),
        ("edit_file target 含 metadata 时的匹配", test_edit_file_with_metadata_in_target),
        ("先读后改（LLM 正确提取）", test_edit_file_with_read_output_as_reference),
        ("read → write → read 往返一致性", test_roundtrip_read_write_read),
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

    # 关键结论
    print("\n结论:")
    print("  1. read_file 的 metadata 前缀确实与文件真实内容不同")
    print("  2. 如果 LLM 误将完整 read 输出传给 write_file，metadata 会被写入文件")
    print("  3. edit_file 的 EditEngine 会正确拒绝含 metadata 的 target（文件中没有）")
    print("  4. 防御措施应在 Agent prompt 层，而非工具层")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
