"""
手动验证脚本：测试 Agent 工具后写内容的正确性

验证范围：
- write_file
- edit_file
- edit_file
- apply_patch_file
- execute_command

运行方式：
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
source .venv/bin/activate
python tests/manual_verify_tool_correctness.py
"""

import asyncio
import hashlib
import os
import sys
import tempfile
import uuid

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.file import safe_read_with_hash, get_file_info
from app.domain.tools.files.write_file import write_file
from app.domain.tools.files.edit_file import edit_file
from app.domain.tools.execution import execute_command


# =============================================================================
# 辅助函数
# =============================================================================

def md5_file(path: str) -> str:
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def make_test_file(content: str) -> str:
    """在工作目录创建临时测试文件"""
    root = os.path.abspath(os.getcwd())
    path = os.path.join(root, f"_test_verify_{uuid.uuid4().hex}.txt")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def cleanup(path: str):
    if path and os.path.exists(path):
        os.unlink(path)


# =============================================================================
# 测试用例
# =============================================================================

async def test_write_file_correctness():
    """验证 write_file 写入内容的正确性"""
    print("\n" + "=" * 60)
    print("TEST: write_file 内容正确性验证")
    print("=" * 60)

    path = make_test_file("")  # 先创建空文件作为占位
    os.unlink(path)

    content = "Hello, EvoLoop!\nLine 2\nLine 3\n"
    result = await write_file.ainvoke({
        "path": path,
        "content": content,
        "overwrite": False
    })
    print(f"Result: {result[:120]}...")

    # 验证 1: 文件存在
    assert os.path.exists(path), "文件未创建"

    # 验证 2: 内容完全匹配
    with open(path, 'r', encoding='utf-8') as f:
        actual = f.read()
    assert actual == content, f"内容不匹配:\n期望: {repr(content)}\n实际: {repr(actual)}"

    # 验证 3: Hash 正确性
    info = get_file_info(path)
    expected_hash = hashlib.md5(content.encode('utf-8')).hexdigest()[:16]
    assert info.content_hash == expected_hash, f"Hash 不匹配: {info.content_hash} != {expected_hash}"

    # 验证 4: 元数据正确
    assert info.total_lines == 3, f"行数错误: {info.total_lines}"
    assert info.size == len(content.encode('utf-8')), f"大小错误: {info.size}"

    cleanup(path)
    print("✅ write_file 内容正确性验证通过")


async def test_edit_file_correctness():
    """验证 edit_file 编辑后内容的正确性"""
    print("\n" + "=" * 60)
    print("TEST: edit_file 编辑后内容正确性验证")
    print("=" * 60)

    original = """def foo():
    return 1

def bar():
    return 2

def baz():
    return 3
"""
    path = make_test_file(original)
    original_hash = md5_file(path)

    # 测试 1: 简单编辑
    result = await edit_file.ainvoke({
        "path": path,
        "target": "    return 1",
        "replacement": "    return 100",
    })
    print(f"Edit result: {result[:100]}...")
    assert "success" in result.lower() or "✅" in result, f"编辑失败: {result}"

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "    return 100" in content, "替换内容不存在"
    assert "    return 1\n" not in content, "旧内容仍存在"
    assert "    return 2" in content, "无关内容被修改"
    assert "    return 3" in content, "无关内容被修改"

    # 测试 2: 带 expected_hash 的编辑（乐观锁）
    _, _, stats = safe_read_with_hash(path)
    current_hash = stats.content_hash

    result2 = await edit_file.ainvoke({
        "path": path,
        "target": "    return 2",
        "replacement": "    return 200",
        "expected_hash": current_hash,
    })
    assert "success" in result2.lower() or "✅" in result2, f"带hash编辑失败: {result2}"

    with open(path, 'r', encoding='utf-8') as f:
        content2 = f.read()
    assert "    return 200" in content2
    assert "    return 100" in content2  # 之前的编辑保留

    # 测试 3: Hash 不匹配时应拒绝编辑
    result3 = await edit_file.ainvoke({
        "path": path,
        "target": "    return 3",
        "replacement": "    return 300",
        "expected_hash": "0000000000000000",
    })
    assert "hash" in result3.lower() or "mismatch" in result3.lower() or "modified" in result3.lower(), \
        f"应检测到hash不匹配: {result3}"

    with open(path, 'r', encoding='utf-8') as f:
        content3 = f.read()
    assert "    return 3" in content3, "hash不匹配时不应修改文件"

    cleanup(path)
    print("✅ edit_file 编辑后内容正确性验证通过")


async def test_edit_file_multiedit_correctness():
    """验证 edit_file 批量编辑的原子性和内容正确性"""
    print("\n" + "=" * 60)
    print("TEST: edit_file 原子性与内容正确性验证")
    print("=" * 60)

    original = """def foo():
    return 1

def bar():
    return 2

def baz():
    return 3
"""
    path = make_test_file(original)
    original_hash = md5_file(path)

    # 测试 1: 全部成功的批量编辑
    edits = [
        {"target": "    return 1", "replacement": "    return 10"},
        {"target": "    return 2", "replacement": "    return 20"},
        {"target": "    return 3", "replacement": "    return 30"},
    ]
    result = await edit_file.ainvoke({"path": path, "edits": edits})
    print(f"MultiEdit result: {result[:100]}...")
    assert "success" in result.lower() or "✅" in result, f"批量编辑失败: {result}"

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "    return 10" in content
    assert "    return 20" in content
    assert "    return 30" in content
    assert "    return 1\n" not in content
    assert "    return 2\n" not in content
    assert "    return 3\n" not in content

    # 测试 2: 原子性回滚 - 任一编辑失败，全部不应应用
    path2 = make_test_file(original)
    edits_fail = [
        {"target": "    return 1", "replacement": "    return 99"},
        {"target": "this does not exist anywhere", "replacement": "should fail"},
    ]
    result2 = await edit_file.ainvoke({"path": path2, "edits": edits_fail})
    print(f"Expected fail result: {result2[:100]}...")
    assert "fail" in result2.lower() or "error" in result2.lower(), f"应失败: {result2}"

    # 验证文件内容完全未变
    after_hash = md5_file(path2)
    assert after_hash == original_hash, "原子性失败：文件被部分修改"

    # 测试 3: 顺序依赖 - 第二个编辑基于第一个编辑的结果
    path3 = make_test_file(original)
    edits_seq = [
        {"target": "    return 1", "replacement": "    return 999"},
        {"target": "    return 999", "replacement": "    return 42"},
    ]
    result3 = await edit_file.ainvoke({"path": path3, "edits": edits_seq})
    assert "success" in result3.lower() or "✅" in result3

    with open(path3, 'r', encoding='utf-8') as f:
        content3 = f.read()
    assert "    return 42" in content3, "顺序编辑最终结果错误"
    assert "    return 999" not in content3, "中间状态残留"
    assert "    return 1" not in content3, "原始状态残留"

    cleanup(path)
    cleanup(path2)
    cleanup(path3)
    print("✅ edit_file 原子性与内容正确性验证通过")


async def test_execute_command_correctness():
    """验证 execute_command 执行命令后输出的正确性"""
    print("\n" + "=" * 60)
    print("TEST: execute_command 命令输出正确性验证")
    print("=" * 60)

    # 测试 1: 简单 echo 命令
    result1 = await execute_command.ainvoke({
        "command": "echo 'hello evoloop'",
        "background": False,
        "timeout": 10
    })
    print(f"Echo result: {result1[:150]}...")
    assert "hello evoloop" in result1, f"echo 输出不正确: {result1}"
    assert "Succeeded" in result1 or "0" in result1, "应显示成功状态"

    # 测试 2: 写文件命令 + read_file 验证（验证命令写入内容的正确性）
    test_path = os.path.join(os.getcwd(), f"_test_cmd_write_{uuid.uuid4().hex}.txt")
    cmd = f"echo 'written by command' > {test_path}"
    result2 = await execute_command.ainvoke({
        "command": cmd,
        "background": False,
        "timeout": 10
    })
    print(f"Write cmd result: {result2[:100]}...")

    # 验证文件内容
    assert os.path.exists(test_path), f"命令未创建文件: {test_path}"
    with open(test_path, 'r', encoding='utf-8') as f:
        file_content = f.read().strip()
    assert file_content == "written by command", f"命令写入内容不正确: {repr(file_content)}"
    os.unlink(test_path)

    # 测试 3: 多行写入验证
    test_path2 = os.path.join(os.getcwd(), f"_test_cmd_write2_{uuid.uuid4().hex}.txt")
    cmd2 = f"printf 'line1\\nline2\\nline3\\n' > {test_path2}"
    result3 = await execute_command.ainvoke({
        "command": cmd2,
        "background": False,
        "timeout": 10
    })

    with open(test_path2, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    assert len(lines) == 3, f"行数不对: {len(lines)}"
    assert lines[0].strip() == "line1"
    assert lines[1].strip() == "line2"
    assert lines[2].strip() == "line3"
    os.unlink(test_path2)

    # 测试 4: 危险命令拦截
    result4 = await execute_command.ainvoke({
        "command": "rm -rf /",
        "background": False,
        "timeout": 10
    })
    print(f"Dangerous cmd result: {result4[:100]}...")
    assert "Security" in result4 or "blocked" in result4.lower() or "error" in result4.lower(), \
        f"应拦截危险命令: {result4}"

    print("✅ execute_command 命令输出正确性验证通过")


# =============================================================================
# 主入口
# =============================================================================

async def main():
    print("\n" + "=" * 60)
    print("Agent 工具后写内容正确性验证套件")
    print("=" * 60)

    passed = 0
    failed = 0

    tests = [
        ("write_file", test_write_file_correctness),
        ("edit_file", test_edit_file_correctness),
        ("edit_file", test_edit_file_multiedit_correctness),
        ("execute_command", test_execute_command_correctness),
    ]

    for name, test_fn in tests:
        try:
            await test_fn()
            passed += 1
        except AssertionError as e:
            print(f"\n❌ {name} 验证失败: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ {name} 运行时错误: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"验证完成: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
