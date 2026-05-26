#!/usr/bin/env python3
"""
PTE 系统完善 - Agent 工具复杂场景写入正确性验证
=====================================================
project_id: 43
验证目标:
  1. edit_file: 多行块替换（替换整个 while 循环体）
  2. edit_file: 多段多行替换（多处循环体 + 新增函数）
  3. apply_patch_file: 复杂多 hunk（新增字段、修改数组、添加新代码块）
  4. write_file + execute_command: 辅助验证
"""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.core.context.manager import ContextManager, EvoContext
from app.domain.tools.files.write_file import write_file
from app.domain.tools.files.edit_file import edit_file
from app.domain.tools.files.apply_patch_file import apply_patch_file
from app.domain.tools.execution import execute_command

PROJECT_PATH = "/Users/huangjinhuan/项目/testProjects/software-ecommerce"

ctx = EvoContext(project_id=43, thread_id=f"pte-complex-{uuid.uuid4().hex[:8]}")
ContextManager.set(ctx)


def read_file(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def read_lines(path: str) -> list:
    with open(path, 'r', encoding='utf-8') as f:
        return f.readlines()


def line_n(path: str, n: int) -> str:
    lines = read_lines(path)
    if 1 <= n <= len(lines):
        return lines[n - 1].rstrip('\n')
    return "[OUT_OF_RANGE]"


def find_line(path: str, text: str) -> int:
    lines = read_lines(path)
    for i, line in enumerate(lines, 1):
        if text in line:
            return i
    return -1


class Report:
    def __init__(self):
        self.items = []

    def add(self, tool: str, check: str, passed: bool, detail: str = ""):
        self.items.append({"tool": tool, "check": check, "passed": passed, "detail": detail})
        icon = "✅" if passed else "❌"
        print(f"  {icon} [{tool}] {check}")
        if detail:
            print(f"     {detail}")

    def summary(self):
        passed = sum(1 for x in self.items if x["passed"])
        total = len(self.items)
        print(f"\n{'='*60}")
        print(f"📊 总计: {passed}/{total} 通过")
        print(f"{'='*60}")
        return passed == total


report = Report()


# ============================================================
# TEST 1: edit_file - 多行块替换（替换整个 while 循环体）
# ============================================================
async def test_edit_file_multiline_block():
    print("\n" + "=" * 60)
    print("TEST 1: edit_file - 多行块替换")
    print("目标: 替换 pte_exam_flow.py 中 Speaking&Writing 的 while 循环体")
    print("=" * 60)

    path = os.path.join(PROJECT_PATH, "pte_exam_flow.py")
    original = read_file(path)
    original_lines = read_lines(path)
    print(f"修改前: {len(original_lines)} 行")

    target = '''    speaking_writing_time = 77 * 60  # 77 minutes in seconds
    speaking_writing_start_time = time.time()
    while time.time() - speaking_writing_start_time < speaking_writing_time and time.time() - exam_start_time < total_exam_time:
        # Simulate tasks within the section
        print("Simulating Speaking & Writing task...")
        time.sleep(1)
        # break #Break for now for testing
    print("Speaking & Writing Section Complete")'''

    replacement = '''    speaking_writing_time = 54 * 60  # 54 minutes in seconds (updated)
    speaking_writing_start_time = time.time()
    section_score = 0
    task_count = 0
    while time.time() - speaking_writing_start_time < speaking_writing_time and time.time() - exam_start_time < total_exam_time:
        # Simulate tasks within the section
        print("Simulating Speaking & Writing task...")
        task_count += 1
        section_score += 85
        time.sleep(1)
    print(f"Speaking & Writing Section Complete - Tasks: {task_count}, Avg Score: {section_score // max(task_count, 1)}")'''

    result = await edit_file.ainvoke({
        "path": path,
        "target": target,
        "replacement": replacement,
    })
    print(f"Tool result: {result[:200]}...")

    after = read_file(path)
    after_lines = read_lines(path)
    print(f"修改后: {len(after_lines)} 行")

    # 验证 1: 旧的多行内容已不存在
    old_still_exists = "77 * 60" in after
    report.add("edit_file", "旧多行块已清除", not old_still_exists)

    # 验证 2: 新的多行内容存在
    new_exists = "task_count += 1" in after and "section_score // max(task_count, 1)" in after
    report.add("edit_file", "新多行块已写入", new_exists)

    # 验证 3: 新内容行号验证
    line_task_count = find_line(path, "task_count += 1")
    line_avg_score = find_line(path, "section_score // max")
    print(f"新内容行号: task_count={line_task_count}, avg_score={line_avg_score}")
    report.add("edit_file", "新块在合理范围内",
               12 <= line_task_count <= 20 and 15 <= line_avg_score <= 25,
               f"task_count 行={line_task_count}, avg_score 行={line_avg_score}")

    # 验证 4: 总行数变化（replacement 比 target 多 3 行）
    # target: 8 行, replacement: 11 行 → +3
    expected_lines = len(original_lines) + 3
    actual_lines = len(after_lines)
    report.add("edit_file", "总行数增加正确", actual_lines == expected_lines,
               f"期望 {expected_lines}, 实际 {actual_lines}")

    # 验证 5: 相邻未修改区域保持原样
    reading_section_ok = "Starting Reading Section" in after
    listening_section_ok = "Starting Listening Section" in after
    report.add("edit_file", "未修改区域保持原样", reading_section_ok and listening_section_ok)

    # 恢复
    with open(path, 'w', encoding='utf-8') as f:
        f.write(original)


# ============================================================
# TEST 2: edit_file - 多段多行替换
# ============================================================
async def test_edit_file_multiedit_complex():
    print("\n" + "=" * 60)
    print("TEST 2: edit_file - 多段多行替换")
    print("目标: 同时修改 3 个 section 的循环体 + 文件末尾新增函数")
    print("=" * 60)

    path = os.path.join(PROJECT_PATH, "pte_exam_flow.py")
    original = read_file(path)
    original_lines = read_lines(path)
    print(f"修改前: {len(original_lines)} 行")

    edits = [
        {
            "target": '''    speaking_writing_time = 77 * 60  # 77 minutes in seconds
    speaking_writing_start_time = time.time()
    while time.time() - speaking_writing_start_time < speaking_writing_time and time.time() - exam_start_time < total_exam_time:
        # Simulate tasks within the section
        print("Simulating Speaking & Writing task...")
        time.sleep(1)
        # break #Break for now for testing
    print("Speaking & Writing Section Complete")''',
            "replacement": '''    speaking_writing_time = 54 * 60  # 54 minutes (updated)
    speaking_writing_start_time = time.time()
    sw_tasks = 0
    while time.time() - speaking_writing_start_time < speaking_writing_time and time.time() - exam_start_time < total_exam_time:
        print("Simulating Speaking & Writing task...")
        sw_tasks += 1
        time.sleep(1)
    print(f"Speaking & Writing Section Complete - Tasks completed: {sw_tasks}")'''
        },
        {
            "target": '''    reading_time = 32 * 60  # 32 minutes in seconds
    reading_start_time = time.time()
    while time.time() - reading_start_time < reading_time and time.time() - exam_start_time < total_exam_time:
        # Simulate tasks within the section
        print("Simulating Reading task...")
        time.sleep(1)
        # break #Break for now for testing
    print("Reading Section Complete")''',
            "replacement": '''    reading_time = 29 * 60  # 29 minutes (updated)
    reading_start_time = time.time()
    reading_tasks = 0
    while time.time() - reading_start_time < reading_time and time.time() - exam_start_time < total_exam_time:
        print("Simulating Reading task...")
        reading_tasks += 1
        time.sleep(1)
    print(f"Reading Section Complete - Tasks completed: {reading_tasks}")'''
        },
        {
            "target": '''    listening_time = 41 * 60  # 41 minutes in seconds
    listening_start_time = time.time()
    while time.time() - listening_start_time < listening_time and time.time() - exam_start_time < total_exam_time:
        # Simulate tasks within the section
        print("Simulating Listening task...")
        time.sleep(1)
        # break #Break for now for testing
    print("Listening Section Complete")''',
            "replacement": '''    listening_time = 30 * 60  # 30 minutes (updated)
    listening_start_time = time.time()
    listening_tasks = 0
    while time.time() - listening_start_time < listening_time and time.time() - exam_start_time < total_exam_time:
        print("Simulating Listening task...")
        listening_tasks += 1
        time.sleep(1)
    print(f"Listening Section Complete - Tasks completed: {listening_tasks}")'''
        },
        {
            "target": '''    print("Exam Complete!")

if __name__ == "__main__":
    exam_flow()''',
            "replacement": '''    print("Exam Complete!")
    generate_exam_report()

if __name__ == "__main__":
    exam_flow()'''
        },
        {
            "target": '''if __name__ == "__main__":
    exam_flow()''',
            "replacement": '''if __name__ == "__main__":
    exam_flow()


def generate_exam_report():
    """Generate a comprehensive PTE exam report."""
    print("=" * 50)
    print("PTE EXAM REPORT")
    print("=" * 50)
    print("Overall Score: 85/100")
    print("Speaking & Writing: 88")
    print("Reading: 82")
    print("Listening: 85")
    print("=" * 50)'''
        },
    ]

    result = await edit_file.ainvoke({"path": path, "edits": edits})
    print(f"Tool result: {result[:200]}...")

    after = read_file(path)
    after_lines = read_lines(path)
    print(f"修改后: {len(after_lines)} 行")

    # 验证 1: 三个 section 的新内容都存在
    has_sw = "sw_tasks += 1" in after
    has_rd = "reading_tasks += 1" in after
    has_ls = "listening_tasks += 1" in after
    report.add("edit_file", "三个 section 新循环体都存在", has_sw and has_rd and has_ls)

    # 验证 2: 旧内容已清除
    old_sw = "77 * 60" in after
    old_rd = "32 * 60" in after
    old_ls = "41 * 60" in after
    report.add("edit_file", "三个旧时间值已清除", not (old_sw or old_rd or old_ls))

    # 验证 3: 行号精确性（注意：multiedit 顺序执行，前面的 edit 会增加行数，导致后面的行号后移）
    # Edit 1: +2 行（原 11-18 行，现仍在 11-20 行范围）
    # Edit 2: 因 Edit 1 增加了 2 行，原 22-29 行 → 现约 24-31 行
    # Edit 3: 因 Edit 1+2 增加了 4 行，原 33-40 行 → 现约 37-44 行
    sw_line = find_line(path, "sw_tasks += 1")
    rd_line = find_line(path, "reading_tasks += 1")
    ls_line = find_line(path, "listening_tasks += 1")
    print(f"新内容行号: SW={sw_line}, RD={rd_line}, LS={ls_line}")
    report.add("edit_file", "Speaking 新块在合理范围", 11 <= sw_line <= 20,
               f"实际行号: {sw_line}")
    report.add("edit_file", "Reading 新块在合理范围", 23 <= rd_line <= 32,
               f"实际行号: {rd_line} (受前面 edit 行数增加影响)")
    report.add("edit_file", "Listening 新块在合理范围", 35 <= ls_line <= 44,
               f"实际行号: {ls_line} (受前面 edits 行数增加影响)")

    # 验证 4: 新增函数存在且位置正确
    has_report = "def generate_exam_report():" in after
    report_line = find_line(path, "def generate_exam_report():")
    total_lines = len(after_lines)
    report.add("edit_file", "新增函数存在", has_report)
    report.add("edit_file", "新增函数在文件末尾附近",
               has_report and report_line >= total_lines - 10,
               f"函数行={report_line}, 总行={total_lines}")

    # 验证 5: generate_exam_report() 调用已插入
    has_call = 'generate_exam_report()' in after
    report.add("edit_file", "函数调用已插入", has_call)

    # 验证 6: 总行数变化（3 处循环体净增 0，Edit4 +1，Edit5 +12 = +13）
    expected = len(original_lines) + 13
    report.add("edit_file", "总行数增加正确",
               len(after_lines) == expected,
               f"期望 {expected}, 实际 {len(after_lines)}")

    # 恢复
    with open(path, 'w', encoding='utf-8') as f:
        f.write(original)


# ============================================================
# TEST 3: apply_patch_file - 复杂多 hunk（单 operation）
# ============================================================
async def test_apply_patch_file_complex():
    print("\n" + "=" * 60)
    print("TEST 3: apply_patch_file - 复杂多 hunk")
    print("目标: 修改 pte.php 的多个题型、新增字段、添加新题型、修改输出")
    print("=" * 60)

    path = os.path.join(PROJECT_PATH, "pte.php")
    if not os.path.exists(path):
        report.add("apply_patch_file", "源文件不存在", False)
        return

    original = read_file(path)
    original_lines = read_lines(path)
    print(f"修改前: {len(original_lines)} 行")

    # CRITICAL: 所有 hunks 必须在同一个 Update File 操作中
    # apply_patch_file 的 bug: 多个 Update File 指向同一文件时，后面的会覆盖前面的
    patch = f"""*** Begin Patch
*** Update File: {path}
@@
-\t'RA' => [
-\t\t'target_accuracy' => 70,   // 目标正确率70%
-\t\t'previous_accuracy' => 0, // 上一周期正确率0%
-\t\t'display_name' => 'Read Aloud'
-\t],
+\t'RA' => [
+\t\t'target_accuracy' => 75,   // 目标正确率75% (updated)
+\t\t'previous_accuracy' => 0,
+\t\t'display_name' => 'Read Aloud',
+\t\t'difficulty' => 'medium'
+\t],
@@
-\t'RO' => [
-\t\t'target_accuracy' => 25,
-\t\t'previous_accuracy' => 16, // 上一周期正确率16%
-\t\t'display_name' => 'Reading: Re-order Paragraphs'
-\t],
+\t'RO' => [
+\t\t'target_accuracy' => 30,   // 提升至30%
+\t\t'previous_accuracy' => 16,
+\t\t'display_name' => 'Reading: Re-order Paragraphs',
+\t\t'difficulty' => 'hard'
+\t],
@@
-\t'WE Core' => [
-\t\t'target_accuracy' => 90,
-\t\t'previous_accuracy' => 0,
-\t\t'display_name' => 'Write Essay (Core)'
-\t],
+\t'WE Core' => [
+\t\t'target_accuracy' => 90,
+\t\t'previous_accuracy' => 0,
+\t\t'display_name' => 'Write Essay (Core)',
+\t\t'difficulty' => 'hard'
+\t],
+\t'SST' => [
+\t\t'target_accuracy' => 80,
+\t\t'previous_accuracy' => 0,
+\t\t'display_name' => 'Summarize Spoken Text',
+\t\t'difficulty' => 'medium'
+\t],
+\t'WFD' => [
+\t\t'target_accuracy' => 85,
+\t\t'previous_accuracy' => 0,
+\t\t'display_name' => 'Write From Dictation',
+\t\t'difficulty' => 'easy'
+\t],
@@
-echo "\\033[1;34mPTE题型正确率分析报告\\033[0m\\n";
-echo "==========================================\\n\\n";
+echo "\\033[1;34mPTE题型正确率分析报告 (v2.0)\\033[0m\\n";
+echo "==========================================\\n";
+echo "报告类型: 周度练习分析\\n\\n";
*** End Patch"""

    result = await apply_patch_file.ainvoke({"patch_text": patch})
    print(f"Tool result: {result[:250]}...")

    after = read_file(path)
    after_lines = read_lines(path)
    print(f"修改后: {len(after_lines)} 行")

    # 验证 1: RA 的 target_accuracy 改为 75
    has_ra_75 = any("target_accuracy" in line and "75" in line for line in after_lines)
    report.add("apply_patch_file", "RA target_accuracy=75", has_ra_75)

    # 验证 2: RA 新增 difficulty 字段
    has_ra_diff = any("difficulty" in line and "medium" in line for line in after_lines)
    report.add("apply_patch_file", "RA 新增 difficulty 字段", has_ra_diff)

    # 验证 3: RO 的 target_accuracy 改为 30
    has_ro_30 = any("target_accuracy" in line and "30" in line for line in after_lines)
    report.add("apply_patch_file", "RO target_accuracy=30", has_ro_30)

    # 验证 4: 新增 SST 和 WFD 题型
    has_sst = "'SST' =>" in after
    has_wfd = "'WFD' =>" in after
    report.add("apply_patch_file", "新增 SST 题型", has_sst)
    report.add("apply_patch_file", "新增 WFD 题型", has_wfd)

    # 验证 5: 新增题型的字段完整
    sst_diff = "'difficulty' => 'medium'" in after
    wfd_diff = "'difficulty' => 'easy'" in after
    report.add("apply_patch_file", "新增题型字段完整", sst_diff and wfd_diff)

    # 验证 6: 标题已更新
    has_v2 = "v2.0" in after
    report.add("apply_patch_file", "报告标题更新为 v2.0", has_v2)

    # 验证 7: 新增报告类型行
    has_report_type = "报告类型: 周度练习分析" in after
    report.add("apply_patch_file", "新增报告类型行", has_report_type)

    # 验证 8: 总行数变化（4 个 hunks，前 3 个各 +1 行，第 4 个 +1 行，新增 SST+WFD +10 行 = +14）
    line_increase = len(after_lines) - len(original_lines)
    report.add("apply_patch_file", "总行数增加合理",
               line_increase >= 10,
               f"原 {len(original_lines)} 行 -> 现 {len(after_lines)} 行 (+{line_increase})")

    # 验证 9: 未修改的题型保持原样
    has_di = "'DI' =>" in after
    has_swt = "'SWT Core' =>" in after
    report.add("apply_patch_file", "未修改题型保持原样", has_di and has_swt)

    # 恢复
    with open(path, 'w', encoding='utf-8') as f:
        f.write(original)


# ============================================================
# 主流程
# ============================================================
async def main():
    print("=" * 60)
    print("🚀 PTE 系统完善 - 复杂场景工具写入正确性验证")
    print(f"📍 Project ID: 43")
    print(f"📂 Project Path: {PROJECT_PATH}")
    print("=" * 60)

    await test_edit_file_multiline_block()
    await test_edit_file_multiedit_complex()
    await test_apply_patch_file_complex()

    return report.summary()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
