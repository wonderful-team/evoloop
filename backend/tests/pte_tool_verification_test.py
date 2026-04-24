#!/usr/bin/env python3
"""
PTE 系统完善测试 - Agent 工具写入正确性验证
================================================
project_id: 43
场景: 完善 PTE 模拟考试系统代码
验证目标: write_file, edit_file, edit_file, apply_patch_file, execute_command
特别验证: 内容写入正确性、行号正确性

运行方式:
    cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
    source .venv/bin/activate
    python tests/pte_tool_verification_test.py
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("pte_tool_verify")

# 降低第三方库日志级别
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

MAX_EXECUTION_TIME = 5 * 60  # 5分钟超时
PROJECT_ID = 43
PROJECT_PATH = "/Users/huangjinhuan/项目/testProjects/software-ecommerce"


# ============================================================
# 工具验证器 - 注册到 Hook 系统拦截工具调用
# ============================================================

class ToolVerificationReport:
    def __init__(self):
        self.records: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0

    def add(self, tool_name: str, tool_args: dict, result: str, detail: str, passed: bool):
        self.records.append({
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "args": tool_args,
            "result_summary": result,
            "detail": detail,
            "passed": passed,
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1

    def print_summary(self):
        print("\n" + "=" * 70)
        print("📊 工具写入正确性验证报告")
        print("=" * 70)
        for i, r in enumerate(self.records, 1):
            icon = "✅" if r["passed"] else "❌"
            print(f"\n{i}. {icon} {r['tool']}")
            print(f"   结果: {r['result_summary']}")
            print(f"   详情: {r['detail']}")
        print(f"\n总计: {self.passed} 通过, {self.failed} 失败")
        print("=" * 70)


report = ToolVerificationReport()


def _get_file_lines(path: str) -> List[str]:
    """读取文件并返回带行号的行列表"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.readlines()
    except Exception as e:
        return [f"[ERROR reading file: {e}]"]


def _get_line_content(path: str, line_num_1_indexed: int) -> str:
    """获取指定行号的内容（1-indexed）"""
    lines = _get_file_lines(path)
    if 1 <= line_num_1_indexed <= len(lines):
        return lines[line_num_1_indexed - 1].rstrip('\n')
    return "[LINE_OUT_OF_RANGE]"


def _count_lines(path: str) -> int:
    return len(_get_file_lines(path))


def _find_line_number(path: str, text: str) -> int:
    """查找文本在文件中的行号（1-indexed），返回第一个匹配或 -1"""
    lines = _get_file_lines(path)
    for i, line in enumerate(lines, 1):
        if text in line:
            return i
    return -1


def _compute_content_hash(content: str) -> str:
    return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]


async def verify_write_file(tool_args: dict, tool_result: str) -> tuple[bool, str]:
    """验证 write_file 写入内容的正确性"""
    path = tool_args.get("path", "")
    expected_content = tool_args.get("content", "")
    if not path or expected_content is None:
        return True, "参数不完整，跳过验证"

    # resolve path
    resolved = os.path.join(PROJECT_PATH, path) if not os.path.isabs(path) else path
    if not os.path.exists(resolved):
        return False, f"文件未创建: {resolved}"

    with open(resolved, 'r', encoding='utf-8') as f:
        actual = f.read()

    if actual != expected_content:
        # 显示差异
        if len(expected_content) < 200 and len(actual) < 200:
            return False, f"内容不匹配:\n期望({len(expected_content)}字): {repr(expected_content)}\n实际({len(actual)}字): {repr(actual)}"
        else:
            return False, f"内容不匹配: 期望 {len(expected_content)} 字符, 实际 {len(actual)} 字符"

    info_hash = _compute_content_hash(actual)
    return True, f"内容完全匹配 ({len(actual)} 字符, hash={info_hash})"


async def verify_edit_file(tool_args: dict, tool_result: str) -> tuple[bool, str]:
    """验证 edit_file 编辑后行号和内容的正确性"""
    path = tool_args.get("path", "")
    target = tool_args.get("target", "")
    replacement = tool_args.get("replacement", "")
    if not path or target is None or replacement is None:
        return True, "参数不完整，跳过验证"

    resolved = os.path.join(PROJECT_PATH, path) if not os.path.isabs(path) else path
    if not os.path.exists(resolved):
        return False, f"文件不存在: {resolved}"

    # 读取文件内容
    with open(resolved, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 验证旧内容已不存在（或至少不存在未替换的副本）
    # 注意：如果 replacement 包含 target 的子串，这里会有误判，所以只检查完全匹配的行
    lines = content.splitlines()
    target_lines = target.splitlines()
    if len(target_lines) == 1 and len(replacement.splitlines()) == 1:
        # 单行替换：检查目标行是否已被替换
        target_found = False
        for line in lines:
            if line.strip() == target.strip():
                target_found = True
                break
        if target_found and target.strip() != replacement.strip():
            return False, f"目标文本仍存在文件中未被替换: {target[:60]}"

    # 2. 验证新内容存在
    if replacement not in content:
        # 可能是多行且换行符不匹配，尝试逐行检查
        repl_lines = replacement.splitlines()
        if len(repl_lines) > 0:
            first_line = repl_lines[0].strip()
            found = any(first_line in line for line in lines)
            if not found:
                return False, f"替换内容未找到: {replacement[:80]}..."

    # 3. 行号验证 - 尝试找到 replacement 的行号
    line_no = -1
    for i, line in enumerate(lines, 1):
        if replacement.splitlines()[0] in line if replacement else False:
            line_no = i
            break

    if line_no > 0:
        return True, f"替换内容出现在第 {line_no} 行，验证通过"
    else:
        return True, f"替换内容存在（行号未精确定位）"


async def verify_edit_file_multiedit(tool_args: dict, tool_result: str) -> tuple[bool, str]:
    """验证 edit_file 批量编辑的正确性"""
    path = tool_args.get("path", "")
    edits = tool_args.get("edits", [])
    if not path or not edits:
        return True, "参数不完整，跳过验证"

    resolved = os.path.join(PROJECT_PATH, path) if not os.path.isabs(path) else path
    if not os.path.exists(resolved):
        return False, f"文件不存在: {resolved}"

    with open(resolved, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.splitlines()
    checks = []
    all_pass = True

    for i, edit in enumerate(edits, 1):
        target = edit.get("target", "") if isinstance(edit, dict) else getattr(edit, "target", "")
        replacement = edit.get("replacement", "") if isinstance(edit, dict) else getattr(edit, "replacement", "")

        if not target:
            continue

        # 检查 replacement 是否存在
        repl_exists = replacement in content
        if not repl_exists and replacement:
            # 尝试首行匹配
            repl_first = replacement.splitlines()[0] if replacement else ""
            repl_exists = any(repl_first in line for line in lines)

        # 检查 target 是否已被替换（不应再存在）
        target_exists = target in content
        if not target_exists and target:
            target_first = target.splitlines()[0] if target else ""
            target_exists = any(target_first in line for line in lines)

        status = "OK"
        if replacement and not repl_exists:
            status = "REPLACEMENT_MISSING"
            all_pass = False
        if target_exists and target.strip() != replacement.strip():
            status = "TARGET_STILL_EXISTS"
            all_pass = False

        checks.append(f"Edit#{i}: {status}")

    detail = "; ".join(checks)
    return all_pass, detail


async def verify_apply_patch_file(tool_args: dict, tool_result: str) -> tuple[bool, str]:
    """验证 apply_patch_file 补丁应用的正确性"""
    patch_text = tool_args.get("patch_text", "")
    if not patch_text:
        return True, "参数不完整，跳过验证"

    # 解析 patch 中的文件路径
    import re
    files_in_patch = re.findall(r'\*\*\*\s+(?:Update|Add|Delete)\s+File:\s*(.+)', patch_text)

    checks = []
    all_pass = True
    for fpath in files_in_patch:
        resolved = os.path.join(PROJECT_PATH, fpath) if not os.path.isabs(fpath) else fpath
        exists = os.path.exists(resolved)
        checks.append(f"{fpath}: exists={exists}")
        # 对于 Add 操作，应该存在；对于 Delete 操作，应该不存在
        # 这里只做基本存在性检查

    return all_pass, f"补丁涉及文件: {'; '.join(checks)}"


async def verify_execute_command(tool_args: dict, tool_result: str) -> tuple[bool, str]:
    """验证 execute_command 执行结果，特别是写文件命令"""
    command = tool_args.get("command", "")
    if not command:
        return True, "参数不完整，跳过验证"

    # 检测是否是写文件命令
    import re
    redirect_match = re.search(r'[>;]\s*(\S+\.(?:py|php|js|ts|json|txt|sql|md|html|css))', command)
    if redirect_match:
        written_file = redirect_match.group(1)
        resolved = os.path.join(PROJECT_PATH, written_file) if not os.path.isabs(written_file) else written_file
        if os.path.exists(resolved):
            size = os.path.getsize(resolved)
            return True, f"检测到文件写入命令，文件已创建 ({size} bytes): {written_file}"
        else:
            # 有些命令可能写入临时目录
            return True, f"命令执行完成 (可能写入非项目目录)"

    return True, f"命令执行完成: {command[:50]}..."


# ============================================================
# Hook 注册
# ============================================================

async def _on_post_tool_use(hook_ctx):
    """POST_TOOL_USE Hook 处理函数"""
    tool_name = hook_ctx.tool_name
    tool_args = hook_ctx.tool_input
    tool_result = hook_ctx.tool_result.output if hook_ctx.tool_result else ""

    # 只关注我们关心的工具
    if tool_name not in ("write_file", "edit_file", "edit_file", "apply_patch_file", "execute_command"):
        return

    logger.info(f"[HOOK] 拦截到 {tool_name}，开始验证写入正确性...")

    try:
        if tool_name == "write_file":
            passed, detail = await verify_write_file(tool_args, tool_result)
        elif tool_name == "edit_file":
            passed, detail = await verify_edit_file(tool_args, tool_result)
        elif tool_name == "edit_file":
            passed, detail = await verify_edit_file_multiedit(tool_args, tool_result)
        elif tool_name == "apply_patch_file":
            passed, detail = await verify_apply_patch_file(tool_args, tool_result)
        elif tool_name == "execute_command":
            passed, detail = await verify_execute_command(tool_args, tool_result)
        else:
            passed, detail = True, "未识别的工具"

        result_summary = "PASS" if passed else "FAIL"
        report.add(tool_name, tool_args, result_summary, detail, passed)

        if passed:
            logger.info(f"[VERIFY] ✅ {tool_name}: {detail}")
        else:
            logger.error(f"[VERIFY] ❌ {tool_name}: {detail}")

    except Exception as e:
        logger.error(f"[VERIFY] ⚠️ 验证过程异常: {e}")
        traceback.print_exc()
        report.add(tool_name, tool_args, "ERROR", str(e), False)


def register_verification_hooks():
    """注册验证 Hook"""
    from app.core.engine.hooks import HookEvent, hook_system
    hook_system.register(HookEvent.POST_TOOL_USE, matcher=".*")(_on_post_tool_use)
    logger.info("[SETUP] 工具验证 Hook 已注册")


# ============================================================
# 环境初始化（轻量版，不清理历史数据）
# ============================================================

async def init_env_light():
    """轻量初始化，不清理数据库，只加载 graph"""
    from app.core.config import settings
    from app.infrastructure.database.sql.database import Base, engine
    from app.infrastructure.database.resource_manager import db_resource_manager
    from sqlmodel import SQLModel

    # 初始化数据库资源管理器
    await db_resource_manager.initialize()

    # 确保表存在（嵌入式模式）
    if settings.EMBEDDED_MODE:
        from app import models
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)

    # 初始化数据
    try:
        from app.initial_data import init as init_data
        await asyncio.to_thread(init_data)
    except:
        pass

    # 初始化 Memory
    try:
        from app.core.memory import MemoryContainer, MemoryConfig
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
    except Exception as e:
        logger.warning(f"Memory 初始化跳过: {e}")

    # 设置 project context
    try:
        from app.core.environment import awaken
        await awaken(project_id=PROJECT_ID)
    except Exception as e:
        logger.warning(f"awaken 跳过: {e}")

    # 构建 Graph
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    import aiosqlite
    db_uri = settings.CHECKPOINTER_DATABASE_URI
    sqlite_path = db_uri.replace("sqlite+aiosqlite://", "").replace("sqlite://", "")
    conn = await aiosqlite.connect(sqlite_path)
    checkpointer = AsyncSqliteSaver(conn=conn)
    await checkpointer.setup()

    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph
    from app.core.persistence import set_checkpointer

    set_checkpointer(checkpointer)
    builder = GraphBuilder()
    config_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/engine/config/agent_main.yaml"
    graph = builder.build(config_path, checkpointer=checkpointer)
    set_graph(graph, config_path=config_path, checkpointer=checkpointer)

    logger.info(f"✅ 环境初始化完成 (Project ID: {PROJECT_ID})")
    return True


# ============================================================
# Agent 对话执行
# ============================================================

async def run_agent_conversation(thread_id: str, message: str, goal: str = "完善PTE系统"):
    """运行单轮 Agent 对话"""
    from app.core.engine.background_agent import run_agent_background
    from app.core.monitoring.activity import activity_monitor

    inputs = {
        "messages": [{"type": "human", "content": message}],
        "project_id": PROJECT_ID,
        "goal": goal,
        "is_retry": False,
    }

    start_time = datetime.now()
    try:
        await asyncio.wait_for(
            run_agent_background(thread_id, inputs),
            timeout=MAX_EXECUTION_TIME
        )
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ Agent 执行完成，耗时 {elapsed:.1f}s")
        return True

    except asyncio.TimeoutError:
        logger.error(f"⏱️ Agent 执行超时 ({MAX_EXECUTION_TIME}s)")
        return False
    except Exception as e:
        logger.error(f"❌ Agent 执行异常: {e}")
        traceback.print_exc()
        return False


# ============================================================
# 主流程
# ============================================================

async def main():
    print("=" * 70)
    print("🚀 PTE 系统完善测试 - Agent 工具写入正确性验证")
    print(f"📍 Project ID: {PROJECT_ID}")
    print(f"📂 Project Path: {PROJECT_PATH}")
    print("=" * 70)

    # 1. 初始化环境
    await init_env_light()

    # 2. 注册验证 Hook
    register_verification_hooks()

    # 3. 设计测试对话 - 明确触发写工具
    thread_id = f"pte-verify-{datetime.now().strftime('%H%M%S')}"

    test_messages = [
        {
            "name": "编辑现有文件",
            "message": (
                "请完善 pte_exam_flow.py 文件，做以下修改:\n"
                "1. 在 exam_flow 函数开始时（print welcome 之后）添加一个计时器初始化: start_time = time.time()\n"
                "2. 将 Speaking & Writing 的考试时间从 77 分钟改为 54 分钟\n"
                "3. 在每个 section 结束后添加分数统计输出，例如 print('Score: 85/100')\n"
                "请使用 edit_file 工具进行修改，修改前先用 read_file 查看文件内容。"
            ),
        },
        {
            "name": "创建新文件",
            "message": (
                "请为 PTE 系统创建一个口语评分模块文件 pte_speaking_scorer.py，包含:\n"
                "1. 一个 SpeakingScorer 类\n"
                "2. 一个 score_fluency 方法，接收音频文件路径，返回流利度分数 (0-100)\n"
                "3. 一个 score_pronunciation 方法，返回发音准确度分数\n"
                "请使用 write_file 工具写入文件。"
            ),
        },
        {
            "name": "批量修改",
            "message": (
                "请批量修改 pte.php 文件:\n"
                "1. 将目标正确率 70% 改为 75%\n"
                "2. 在学习建议部分添加一条新建议: '5. 定期进行模拟考试以检测进度'\n"
                "请使用 edit_file(edits=...) 工具完成。"
            ),
        },
        {
            "name": "执行命令验证",
            "message": (
                "请执行命令 `python pte_exam_flow.py` 来验证修改后的代码能否正常运行，"
                "并将输出保存到 pte_test_output.txt 文件中。"
            ),
        },
    ]

    for test in test_messages:
        print(f"\n{'-' * 70}")
        print(f"📝 测试任务: {test['name']}")
        print(f"💬 用户消息: {test['message'][:100]}...")
        print(f"{'-' * 70}")

        success = await run_agent_conversation(thread_id, test["message"], goal="完善PTE模拟考试系统")
        if not success:
            print("⚠️ 该任务执行失败或超时，继续下一个...")

        # 轮间等待，让系统稳定
        await asyncio.sleep(3)

    # 4. 输出验证报告
    report.print_summary()

    # 5. 最终文件状态检查
    print("\n" + "=" * 70)
    print("📂 最终文件状态检查")
    print("=" * 70)

    files_to_check = [
        "pte_exam_flow.py",
        "pte_speaking_scorer.py",
        "pte.php",
        "pte_test_output.txt",
    ]

    for fname in files_to_check:
        fpath = os.path.join(PROJECT_PATH, fname)
        if os.path.exists(fpath):
            size = os.path.getsize(fpath)
            lines = _count_lines(fpath)
            print(f"✅ {fname}: {size} bytes, {lines} lines")
        else:
            print(f"❌ {fname}: 不存在")

    print("\n" + "=" * 70)
    print("🏁 测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
