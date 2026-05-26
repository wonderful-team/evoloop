#!/usr/bin/env python3
"""
PTE 系统完善 - Agent 工具写入正确性直接验证
===============================================
project_id: 43
场景: 在 software-ecommerce 项目的 PTE 代码上进行真实修改并验证

验证工具: write_file, edit_file, edit_file, apply_patch_file, execute_command
核心验证: 内容写入正确性、行号精确性
"""

import asyncio
import hashlib
import os
import sys
import tempfile
import uuid
from datetime import datetime

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.core.context.manager import ContextManager, EvoContext
from app.core.file import get_file_info, safe_read_with_hash
from app.domain.tools.files.write_file import write_file
from app.domain.tools.files.edit_file import edit_file
from app.domain.tools.files.apply_patch_file import apply_patch_file
from app.domain.tools.execution import execute_command

PROJECT_PATH = "/Users/huangjinhuan/项目/testProjects/software-ecommerce"
TEST_PATH = os.path.join(PROJECT_PATH, f"_agent_verify_test_{uuid.uuid4().hex[:8]}")

# 设置 project 上下文
ctx = EvoContext(project_id=43, thread_id=f"pte-verify-{uuid.uuid4().hex[:8]}")
ContextManager.set(ctx)


class VerifyReport:
    def __init__(self):
        self.results = []

    def add(self, tool: str, desc: str, passed: bool, detail: str = ""):
        self.results.append({"tool": tool, "desc": desc, "passed": passed, "detail": detail})
        icon = "✅" if passed else "❌"
        print(f"  {icon} {tool}: {desc}")
        if detail:
            print(f"     {detail}")

    def summary(self):
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        print(f"\n📊 总计: {passed}/{total} 通过")
        return passed == total


report = VerifyReport()


def read_lines(path: str) -> list:
    with open(path, 'r', encoding='utf-8') as f:
        return f.readlines()


def line_content(path: str, line_no_1_indexed: int) -> str:
    lines = read_lines(path)
    if 1 <= line_no_1_indexed <= len(lines):
        return lines[line_no_1_indexed - 1].rstrip('\n')
    return "[OUT_OF_RANGE]"


def find_line(path: str, text: str) -> int:
    lines = read_lines(path)
    for i, line in enumerate(lines, 1):
        if text in line:
            return i
    return -1


# ============================================================
# 1. write_file 验证
# ============================================================
async def test_write_file():
    print("\n" + "=" * 60)
    print("TEST 1: write_file - 创建 PTE 口语评分模块")
    print("=" * 60)

    content = '''"""PTE Speaking Scorer Module"""
import time
from typing import Dict, Any

class SpeakingScorer:
    """PTE 口语评分器"""

    def __init__(self):
        self.model_loaded = False
        self.load_time = time.time()

    def score_fluency(self, audio_path: str) -> int:
        """评估流利度 (0-100)"""
        # TODO: 集成语音识别模型
        return 85

    def score_pronunciation(self, audio_path: str) -> int:
        """评估发音准确度 (0-100)"""
        # TODO: 集成发音评估模型
        return 80

    def get_overall_score(self, audio_path: str) -> Dict[str, Any]:
        """获取综合评分"""
        return {
            "fluency": self.score_fluency(audio_path),
            "pronunciation": self.score_pronunciation(audio_path),
            "overall": (self.score_fluency(audio_path) + self.score_pronunciation(audio_path)) // 2
        }
'''
    path = os.path.join(PROJECT_PATH, "pte_speaking_scorer_agent.py")

    result = await write_file.ainvoke({
        "path": path,
        "content": content,
        "overwrite": True,
    })
    print(f"Tool result: {result[:120]}...")

    # 验证 1: 文件存在
    exists = os.path.exists(path)
    report.add("write_file", "文件是否创建", exists)

    # 验证 2: 内容完全匹配
    with open(path, 'r', encoding='utf-8') as f:
        actual = f.read()
    content_match = actual == content
    report.add("write_file", "内容完全匹配", content_match,
               f"期望 {len(content)} 字符, 实际 {len(actual)} 字符")

    # 验证 3: 行号正确性 - 检查特定行
    lines = read_lines(path)
    line_checks = [
        (1, '"""PTE Speaking Scorer Module"""'),
        (8, "    def __init__(self):"),
        (12, "    def score_fluency(self, audio_path: str) -> int:"),
        (22, "    def get_overall_score(self, audio_path: str) -> Dict[str, Any]:"),
    ]
    for expected_line, expected_text in line_checks:
        actual_text = line_content(path, expected_line)
        passed = expected_text in actual_text
        report.add("write_file", f"第 {expected_line} 行内容正确", passed,
                   f"期望: {expected_text[:40]}... | 实际: {actual_text[:40]}...")

    # 清理
    if os.path.exists(path):
        os.unlink(path)


# ============================================================
# 2. edit_file 验证 - 单行替换 + 行号验证
# ============================================================
async def test_edit_file():
    print("\n" + "=" * 60)
    print("TEST 2: edit_file - 修改 pte_exam_flow.py")
    print("=" * 60)

    path = os.path.join(PROJECT_PATH, "pte_exam_flow.py")
    if not os.path.exists(path):
        report.add("edit_file", "源文件不存在", False, path)
        return

    # 记录修改前的行号和内容
    before_lines = read_lines(path)
    original_line_12 = line_content(path, 12)  # speaking_writing_time = 77 * 60
    original_line_count = len(before_lines)
    print(f"修改前: {original_line_count} 行")
    print(f"修改前第 12 行: {original_line_12}")

    # 执行 edit_file: 修改 77 分钟为 54 分钟
    result = await edit_file.ainvoke({
        "path": path,
        "target": "    speaking_writing_time = 77 * 60  # 77 minutes in seconds",
        "replacement": "    speaking_writing_time = 54 * 60  # 54 minutes in seconds (updated)",
    })
    print(f"Tool result: {result[:150]}...")

    # 验证 1: 旧内容已不存在
    after_lines = read_lines(path)
    has_old = any("77 * 60" in line for line in after_lines)
    report.add("edit_file", "旧内容已清除", not has_old)

    # 验证 2: 新内容存在
    has_new = any("54 * 60" in line for line in after_lines)
    report.add("edit_file", "新内容已写入", has_new)

    # 验证 3: 行号保持不变（单行替换应该在同一行）
    line_12_after = line_content(path, 12)
    line_no_new = find_line(path, "54 * 60")
    print(f"修改后第 12 行: {line_12_after}")
    print(f"新内容所在行号: {line_no_new}")

    report.add("edit_file", "替换发生在第 12 行", line_no_new == 12,
               f"期望行号: 12, 实际行号: {line_no_new}")

    # 验证 4: 总行数不变（单行替换不应改变行数）
    after_line_count = len(after_lines)
    report.add("edit_file", "总行数不变", after_line_count == original_line_count,
               f"期望: {original_line_count}, 实际: {after_line_count}")

    # 验证 5: 相邻行未受影响
    line_11 = line_content(path, 11)
    line_13 = line_content(path, 13)
    report.add("edit_file", "相邻行未变",
               "Speaking & Writing Section" in line_11 and "speaking_writing_start_time" in line_13)

    # 恢复文件（回滚修改）
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(before_lines)


# ============================================================
# 3. edit_file 验证 - 批量修改 + 行号验证
# ============================================================
async def test_edit_file_multiedit():
    print("\n" + "=" * 60)
    print("TEST 3: edit_file - 批量修改 pte_exam_flow.py")
    print("=" * 60)

    path = os.path.join(PROJECT_PATH, "pte_exam_flow.py")
    if not os.path.exists(path):
        report.add("edit_file", "源文件不存在", False)
        return

    before_lines = read_lines(path)
    original_line_count = len(before_lines)
    print(f"修改前: {original_line_count} 行")

    # 记录修改前的关键行
    line_11_before = line_content(path, 11)
    line_22_before = line_content(path, 22)
    line_33_before = line_content(path, 33)

    edits = [
        {"target": "    print(\"Starting Speaking & Writing Section\")",
         "replacement": "    print(\"Starting Speaking & Writing Section [UPDATED]\")"},
        {"target": "    print(\"Starting Reading Section\")",
         "replacement": "    print(\"Starting Reading Section [UPDATED]\")"},
        {"target": "    print(\"Starting Listening Section\")",
         "replacement": "    print(\"Starting Listening Section [UPDATED]\")"},
    ]

    result = await edit_file.ainvoke({"path": path, "edits": edits})
    print(f"Tool result: {result[:150]}...")

    after_lines = read_lines(path)
    after_line_count = len(after_lines)

    # 验证 1: 三个新内容都存在
    has_1 = any("Speaking & Writing Section [UPDATED]" in line for line in after_lines)
    has_2 = any("Reading Section [UPDATED]" in line for line in after_lines)
    has_3 = any("Listening Section [UPDATED]" in line for line in after_lines)
    report.add("edit_file", "三个替换都生效", has_1 and has_2 and has_3)

    # 验证 2: 行号正确性 - 替换应该在原行号上
    line_11_after = find_line(path, "Speaking & Writing Section [UPDATED]")
    line_22_after = find_line(path, "Reading Section [UPDATED]")
    line_33_after = find_line(path, "Listening Section [UPDATED]")

    print(f"行号对比: Speaking={line_11_after}(期望11), Reading={line_22_after}(期望22), Listening={line_33_after}(期望33)")

    report.add("edit_file", "Speaking 替换行号=11", line_11_after == 11)
    report.add("edit_file", "Reading 替换行号=22", line_22_after == 22)
    report.add("edit_file", "Listening 替换行号=33", line_33_after == 33)

    # 验证 3: 总行数不变
    report.add("edit_file", "总行数不变", after_line_count == original_line_count,
               f"{original_line_count} -> {after_line_count}")

    # 恢复
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(before_lines)


# ============================================================
# 4. apply_patch_file 验证 - 补丁应用 + 行号验证
# ============================================================
async def test_apply_patch_file():
    print("\n" + "=" * 60)
    print("TEST 4: apply_patch_file - 结构化修改")
    print("=" * 60)

    # 先创建一个测试文件
    test_file = os.path.join(PROJECT_PATH, f"_patch_test_{uuid.uuid4().hex[:6]}.py")
    original_content = '''def exam_flow():
    print("Welcome to PTE")
    total_time = 3 * 60 * 60

    # Speaking
    print("Starting Speaking")
    speaking_time = 30 * 60

    # Reading
    print("Starting Reading")
    reading_time = 32 * 60

    # Listening
    print("Starting Listening")
    listening_time = 41 * 60

    print("Exam Complete!")
'''
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(original_content)

    print(f"测试文件: {test_file}")
    before_lines = read_lines(test_file)
    print(f"修改前: {len(before_lines)} 行")

    # 构建 patch: 修改两个 section 的时间，并添加 Writing
    patch = f"""*** Begin Patch
*** Update File: {test_file}
@@
-    # Speaking
-    print("Starting Speaking")
-    speaking_time = 30 * 60
+    # Speaking & Writing
+    print("Starting Speaking & Writing")
+    speaking_time = 54 * 60
@@
-    # Listening
-    print("Starting Listening")
-    listening_time = 41 * 60
+    # Listening
+    print("Starting Listening")
+    listening_time = 45 * 60
+    print("Listening time updated to 45 min")
*** End Patch"""

    result = await apply_patch_file.ainvoke({"patch_text": patch})
    print(f"Tool result: {result[:150]}...")

    after_lines = read_lines(test_file)
    print(f"修改后: {len(after_lines)} 行")

    # 验证 1: 第一处修改（3行变3行，但内容变了）
    line_speaking = find_line(test_file, "Starting Speaking & Writing")
    report.add("apply_patch_file", "Speaking & Writing 修改生效", line_speaking > 0,
               f"所在行号: {line_speaking}")

    # 验证 2: 第二处修改（3行变4行，新增一行）
    line_listening = find_line(test_file, "Listening time updated to 45 min")
    report.add("apply_patch_file", "Listening 新增行生效", line_listening > 0,
               f"新增行所在行号: {line_listening}")

    # 验证 3: 总行数变化正确（3->3, 3->4，净增1行）
    expected_lines = len(before_lines) + 1
    actual_lines = len(after_lines)
    report.add("apply_patch_file", "总行数正确", actual_lines == expected_lines,
               f"期望 {expected_lines}, 实际 {actual_lines}")

    # 验证 4: 未修改部分保持原样
    line_exam_complete = find_line(test_file, "Exam Complete!")
    report.add("apply_patch_file", "未修改部分保留", line_exam_complete > 0,
               f"Exam Complete! 所在行: {line_exam_complete}")

    # 清理
    if os.path.exists(test_file):
        os.unlink(test_file)


# ============================================================
# 5. execute_command 验证 - 命令执行 + 文件写入
# ============================================================
async def test_execute_command():
    print("\n" + "=" * 60)
    print("TEST 5: execute_command - 执行命令并验证输出")
    print("=" * 60)

    # 测试 1: echo 命令
    result = await execute_command.ainvoke({
        "command": "echo 'PTE verification test'",
        "background": False,
        "timeout": 10,
    })
    has_output = "PTE verification test" in result
    report.add("execute_command", "echo 输出正确", has_output)

    # 测试 2: 写文件命令
    test_file = os.path.join(PROJECT_PATH, f"_cmd_test_{uuid.uuid4().hex[:6]}.txt")
    result2 = await execute_command.ainvoke({
        "command": f"echo 'written by execute_command' > {test_file}",
        "background": False,
        "timeout": 10,
    })

    file_exists = os.path.exists(test_file)
    report.add("execute_command", "命令创建文件成功", file_exists)

    if file_exists:
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        content_correct = content == "written by execute_command"
        report.add("execute_command", "命令写入内容正确", content_correct,
                   f"期望: 'written by execute_command', 实际: '{content}'")
        os.unlink(test_file)

    # 测试 3: 危险命令拦截
    result3 = await execute_command.ainvoke({
        "command": "rm -rf /",
        "background": False,
        "timeout": 10,
    })
    blocked = "Security" in result3 or "blocked" in result3.lower()
    report.add("execute_command", "危险命令被拦截", blocked)


# ============================================================
# 主流程
# ============================================================
async def main():
    print("=" * 60)
    print("🚀 PTE 系统完善 - Agent 工具写入正确性验证")
    print(f"📍 Project ID: 43")
    print(f"📂 Project Path: {PROJECT_PATH}")
    print("=" * 60)
    print("\n本测试直接调用 Agent 工具函数，在真实项目代码上执行")
    print("并详细验证写入内容的正确性和行号精确性。\n")

    await test_write_file()
    await test_edit_file()
    await test_edit_file_multiedit()
    await test_apply_patch_file()
    await test_execute_command()

    print("\n" + "=" * 60)
    print("📊 最终验证报告")
    print("=" * 60)
    all_passed = report.summary()

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
