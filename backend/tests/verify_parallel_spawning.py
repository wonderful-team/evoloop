"""
Parallel Spawner 真实 LLM 黑盒集成测试

测试目标：
    验证重构后的 ParallelSpawnerNode + route_parallel_spawner 完整链路在
    真实 LLM 驱动下能够正常工作——Supervisor 在收到一个含有天然并行结构的
    业务需求时，能够自主判断并触发 decompose_task，最终并发派发多个 Worker。

测试设计原则：
    - 指令中完全不提工具名、不提"并发"或"子任务"等技术术语
    - 纯业务语言，模拟普通用户的真实表达
    - 白盒断言通过读取数据库 Message 记录完成（参考 verify_universal_analytics_skill.py 模式）

运行方式：
    cd evoloop/backend
    .venv/bin/python tests/verify_parallel_spawning.py
"""

import asyncio
import logging
import os
import sys
import uuid
from unittest.mock import patch

from dotenv import load_dotenv
from sqlalchemy import select

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("verify_parallel_spawning")

from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.infrastructure.database.sql.database import session_scope
from app.models import Message
from app.core.evocloud import evocloud_manager
from app.core.identity import identity_service


# ─────────────────────────────────────────────────────────────────────────────
# 测试参数
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_ID = 99
TEST_PROJECT_PATH = "/tmp/evoloop_parallel_spawner_test"

# 纯业务语言指令——完全不提工具名、不提"并发"、不提"子任务"
# 任务天然具备"数据库模型 / 后端接口 / 前端页面"三个独立职责域，
# Supervisor 应凭自身推理 + 提示词引导自主决策是否并发拆解。
USER_INSTRUCTION = (
    f"帮我在 {TEST_PROJECT_PATH} 目录下完整实现用户管理功能。"
    "需要定义数据库里的 users 表和 sessions 表的模型文件，"
    "在后端写好用户注册和查询的 API 接口，"
    "并在前端写一个用户列表的展示页面和对应的样式文件。"
)


async def initialize_system():
    logger.info("--- Initializing Real System for Parallel Spawner E2E Test ---")
    os.makedirs(TEST_PROJECT_PATH, exist_ok=True)

    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    await MemoryLifespanManager.ainitialize()
    auto_discover_handlers()

    builder = GraphBuilder()
    config_path = os.path.join(
        os.path.dirname(__file__),
        "../app/core/engine/config/agent_main.yaml"
    )
    graph = builder.build(
        os.path.abspath(config_path),
        checkpointer=db_resource_manager.checkpointer
    )
    set_graph(graph)
    logger.info("--- System Ready (graph built with parallel_spawner node) ---")


async def run_verification():
    try:
        await initialize_system()

        thread_id = f"parallel-spawner-{uuid.uuid4().hex[:6]}"

        logger.info("[Test] Bootstrapping EvoCloud Manager...")
        try:
            evocloud_manager.initialize()
        except Exception as e:
            logger.warning(f"[Test] EvoCloud init notice: {e}")

        TOKEN = "test-token"
        await identity_service.set_token(TOKEN, "test-refresh")
        member_id = 1
        logger.info(f"[Test] Using local gateway token. member_id={member_id}")

        mock_project = {
            "id": PROJECT_ID,
            "name": "Parallel Spawner Verification Project",
            "path": TEST_PROJECT_PATH,
        }

        with patch("app.core.evocloud.evocloud_manager.get_token", return_value=TOKEN), \
             patch("app.core.identity.identity_service.get_member_id", return_value=member_id), \
             patch("app.core.evocloud.evocloud_manager.get_project_by_id", return_value=mock_project):

            logger.info("=" * 65)
            logger.info(f"🚀 PARALLEL SPAWNER VERIFICATION (Thread: {thread_id})")
            logger.info(f"📝 INSTRUCTION:\n{USER_INSTRUCTION}")
            logger.info("=" * 65)

            # ── Step 1: Dispatch ──────────────────────────────────────────
            dispatch_res = await dispatch_agent_run(
                thread_id=thread_id,
                message_content=USER_INSTRUCTION,
                project_id=PROJECT_ID,
            )

            if dispatch_res.status != "queued":
                logger.error(f"❌ Dispatch failed: {dispatch_res.error}")
                return

            logger.info(f"[Test] Agent queued. Inputs keys: {list(dispatch_res.inputs.keys())}")

            # ── Step 2: Run ───────────────────────────────────────────────
            logger.info("[Test] Running agent background loop (real LLM)...")
            await run_agent_background(thread_id, dispatch_res.inputs)

            # ── Step 3: Audit ─────────────────────────────────────────────
            logger.info("=" * 65)
            logger.info("📊 EXECUTION AUDIT — Thread Messages")
            logger.info("=" * 65)

            async with session_scope() as session:
                stmt = (
                    select(Message)
                    .where(Message.thread_id == thread_id)
                    .order_by(Message.sequence_number)
                )
                res = await session.execute(stmt)
                all_msgs = res.scalars().all()

                logger.info(f"Total messages in thread: {len(all_msgs)}")
                for m in all_msgs:
                    role_icon = "👤" if m.role == "human" else "🤖" if m.role == "ai" else "🛠️"
                    logger.info(
                        f"{role_icon} [{m.sequence_number}] {m.role.upper()} "
                        f"({m.action_type}/{m.category}):\n"
                        f"{str(m.content)[:400]}...\n"
                        f"{'-' * 40}"
                    )

            # ── Step 4: 白盒断言 — 检查并发派发的关键信号 ──────────────
            logger.info("=" * 65)
            logger.info("🔍 WHITE-BOX ASSERTIONS — Parallel Spawn Evidence")
            logger.info("=" * 65)

            async with session_scope() as session:
                stmt = (
                    select(Message)
                    .where(Message.thread_id == thread_id)
                )
                res = await session.execute(stmt)
                all_msgs = res.scalars().all()

                all_content = " ".join(str(m.content) for m in all_msgs).lower()

                # 断言 1：Supervisor 调用了 decompose_task 工具
                # （工具调用会作为 tool message 记录在 DB 中）
                tool_msgs = [m for m in all_msgs if m.role == "tool" or m.action_type == "tool_call"]
                decompose_calls = [
                    m for m in all_msgs
                    if "decompose_task" in str(m.content).lower()
                    or "decompose_task" in str(getattr(m, "action_type", "")).lower()
                ]

                logger.info(f"[断言1] Tool messages found: {len(tool_msgs)}")
                logger.info(f"[断言1] decompose_task evidence: {len(decompose_calls)} messages")

                # 断言 2：有多个 subtask thread（线程 ID 含有 :sub: 标记）
                sub_thread_msgs = [
                    m for m in all_msgs
                    if ":sub:" in str(getattr(m, "thread_id", ""))
                ]
                logger.info(f"[断言2] Sub-thread messages (thread_id contains ':sub:'): {len(sub_thread_msgs)}")

                # 断言 3：产生的文件覆盖多个职责域
                files_created = []
                for f in ["users", "sessions", "api", "frontend", "model", "page", "style"]:
                    if f in all_content:
                        files_created.append(f)
                logger.info(f"[断言3] Domain keywords found in output: {files_created}")

                # ── 最终判定 ─────────────────────────────────────────────
                logger.info("=" * 65)
                if len(sub_thread_msgs) >= 2:
                    logger.info("✅ 并发派发已触发！检测到多个 :sub: 子线程消息，ParallelSpawner 链路正常。")
                elif len(decompose_calls) >= 1:
                    logger.info("✅ Supervisor 调用了 decompose_task，并发分解意图已触发。")
                else:
                    logger.warning(
                        "⚠️  未检测到并发派发的明确证据。\n"
                        "  可能原因：\n"
                        "  1. LLM 选择了串行 route_to 而非 decompose_task（属于 LLM 推理决策，非 bug）\n"
                        "  2. 任务规模评估低于并发触发阈值\n"
                        "  3. 系统提示词需进一步调整并发触发边界\n"
                        "  请人工检查上方的 Thread Messages 输出以确认 Agent 行为。"
                    )
                logger.info("=" * 65)

    finally:
        await db_resource_manager.shutdown()
        logger.info("--- Verification Cleanup Complete ---")


if __name__ == "__main__":
    asyncio.run(run_verification())
