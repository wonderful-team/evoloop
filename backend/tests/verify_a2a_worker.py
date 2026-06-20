"""
verify_a2a_worker.py
====================
A2A 集成测试 — Worker 端验证脚本

用途：
  在 Worker 实例（PORT=20161, EVOLOOP_APP_DATA_DIR=~/.evoloop_worker）的进程中运行。
  登录 EvoCloud，然后模拟一个来自 Caller 的 A2A 任务，直接驱动 Worker 的 Agent Loop
  执行任务（下载附件、验证内容、保存文件、调用 complete_task 返回结果）。

  这样可以独立测试 Worker 端的 LLM + 工具执行链，无需依赖完整的 Gateway 消息路由。

运行方式（在 evoloop/backend 目录下）：
  EVOCLOUD_API_URL=http://localhost:8082 \\
  EVOCLOUD_WS_URL=ws://localhost:9001/ws \\
  EVOCLOUD_DEVICE_TYPE=server \\
  EVOCLOUD_DEVICE_CAPABILITIES=deployment,docker_ops \\
  EVOCLOUD_DEVICE_NAME=Worker-Server \\
  EVOLOOP_APP_DATA_DIR=/Users/huangjinhuan/.evoloop_worker \\
  PORT=20161 \\
  ./.venv/bin/python tests/verify_a2a_worker.py
"""

import asyncio
import logging
import os
import sys
import time
import uuid

# 将 backend 目录添加到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("verify_a2a_worker")

# ─── 依赖导入 ────────────────────────────────────────────────────────────────

from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.core.evocloud import evocloud_manager
from app.core.identity import identity_service


# ─── 系统初始化 ───────────────────────────────────────────────────────────────

async def initialize_system():
    logger.info("--- [Worker] 初始化系统（DB / Memory / Graph）---")
    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    await MemoryLifespanManager.ainitialize()
    auto_discover_handlers()

    builder = GraphBuilder()
    config_path = os.path.join(
        os.path.dirname(__file__),
        "../app/core/engine/config/agent_main.yaml",
    )
    graph = builder.build(
        os.path.abspath(config_path),
        checkpointer=db_resource_manager.checkpointer,
    )
    set_graph(graph)
    logger.info("--- [Worker] 系统初始化完成 ---")


# ─── 登录 ─────────────────────────────────────────────────────────────────────

async def login(username: str = "preterchan", password: str = "hellomylife"):
    logger.info(f"[Worker] 正在登录 EvoCloud（用户：{username}）...")
    try:
        evocloud_manager.initialize()
    except Exception as e:
        logger.warning(f"[Worker] EvoCloud manager 初始化提示：{e}")

    client = evocloud_manager.api
    login_res = await client.login(username, password)
    if not login_res.get("success"):
        raise RuntimeError(f"[Worker] 登录失败：{login_res}")

    token = login_res["token"]
    refresh_token = login_res.get("refresh_token", "")
    await identity_service.set_token(token, refresh_token)
    member_id = await identity_service.get_member_id(token) or 1
    logger.info(f"[Worker] 登录成功。member_id={member_id}")
    return token, member_id


async def fetch_default_model() -> str:
    """
    从 Gateway 拉取可用模型列表，取第一个 evoloop 类型的 LLM 模型作为默认模型。
    这样不依赖本地 SystemConfigService DB 里的 LLM_MODEL 配置。
    """
    client = evocloud_manager.api
    resp = await client.get_llm_models()
    if resp.get("code") != 0:
        raise RuntimeError(f"[Worker] 获取模型列表失败：{resp}")

    models = resp.get("data", {}).get("models", [])
    for m in models:
        if m.get("config_type") == "evoloop" and m.get("model_type") == "llm":
            model_id = m["model_id"]
            logger.info(f"[Worker] 使用 Gateway 下发的默认模型：{model_id} ({m.get('display_name')})")
            return model_id

    raise RuntimeError(f"[Worker] 没有可用的 evoloop LLM 模型，请在后台配置")


# ─── 准备附件（模拟 Caller 上传的 deploy_info.txt）──────────────────────────

def prepare_test_attachment() -> str:
    """
    在本地创建 deploy_info.txt 并返回路径。
    实际场景中附件通过 Gateway 下载，这里直接创建本地文件模拟已下载。
    """
    attach_dir = os.path.expanduser("~/.evoloop_worker/attachments/task-local-test")
    os.makedirs(attach_dir, exist_ok=True)
    dest_path = os.path.join(attach_dir, "deploy_info.txt")
    with open(dest_path, "w") as f:
        f.write("Hello Go Gateway")
    logger.info(f"[Worker] 测试附件已准备：{dest_path}")
    return dest_path


# ─── 主验证逻辑 ───────────────────────────────────────────────────────────────

async def run_verification():
    try:
        await initialize_system()
        await login()

        # 唤醒 Agent 环境
        from app.core.environment import awaken
        await awaken(project_id=0)

        # 从 Gateway 拉取默认模型（绕过本地未配置 LLM_MODEL 的问题）
        default_model = await fetch_default_model()

        # 模拟一个 A2A 任务 thread_id（实际场景由 Caller 生成）
        task_id = f"task-local-test-{uuid.uuid4().hex[:8]}"
        thread_id = task_id

        # 模拟附件已下载到本地
        attachment_path = prepare_test_attachment()

        logger.info("=" * 60)
        logger.info(f"🚀 [Worker] 启动 A2A Worker 任务测试（Task: {task_id}）")
        logger.info("=" * 60)

        # Worker 的任务指令（与真实 A2A 任务中的 instruction 字段相同）
        instruction = (
            "请将收到的附件 deploy_info.txt 作为测试部署包部署到本机。"
            "验证文件中包含 \"Hello Go Gateway\"，"
            "并将其保存到 /tmp/deploy_info.txt 路径，"
            "然后返回部署结果：文件是否存在、保存路径、文件内容。"
            "如果无法写入 /tmp，请选择一个合适的可写目录保存并返回实际路径。"
        )

        # 系统上下文（模拟 A2A subscriber 注入的 system message）
        system_context = (
            "[A2A System Context]\n"
            "You are executing a subtask initiated by device key: evo_9cc6ce7b64034de2b87e101adde1a83a.\n"
            "Caller Role: desktop\n"
            "Global Goal: 请使用 list_agents 工具查找在线的 server 部署设备，并把一个测试部署包部署到它上面。"
            "你可以先生成一个叫 deploy_info.txt 的测试文本，写入 Hello Go Gateway 并在发送任务时将其作为附件带上。\n"
            f"Instruction: {instruction}\n"
            f"Attachments downloaded locally at: {attachment_path}\n"
            "\nRequirements:\n"
            "1. You must execute this subtask in this thread.\n"
            "2. When done, you must call the `complete_task` tool exactly once to return success or failure.\n"
            "Do not carry out unnecessary conversation."
        )

        # 先在 DB 中创建 Conversation
        from app.models import Conversation
        from app.infrastructure.database.sql.database import session_scope
        from datetime import datetime, timezone

        async with session_scope() as session:
            conv = await session.get(Conversation, thread_id)
            if not conv:
                conv = Conversation(
                    id=thread_id,
                    project_id=0,
                    title=f"A2A Worker Test: {task_id}",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(conv)

        # 持久化 system message（与 _handle_a2a_task 相同的方式）
        from app.core.engine.message.repository import MessageRepository
        repo = MessageRepository(thread_id, project_id=0)
        await repo.persist(
            role="system",
            content=system_context,
            category="internal_system",
            is_visible=True,
        )

        start_time = time.time()
        logger.info("[Worker] 正在调度 Agent Run...")

        dispatch_res = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=instruction,
            project_id=0,
            model=default_model,  # 显式传入从 Gateway 拉取的模型
            metadata={
                "task_type": "a2a_task",
                "task_id": task_id,
                "caller_device_key": "evo_9cc6ce7b64034de2b87e101adde1a83a",
                "root_thread_id": "0cdf6146-7300-4beb-bf11-81856c411837",
                "parent_thread_id": "0cdf6146-7300-4beb-bf11-81856c411837",
            },
        )

        if dispatch_res.status != "queued":
            logger.error(f"❌ [Worker] Dispatch 失败：{dispatch_res.error}")
            return

        logger.info(f"[Worker] Agent 已排队（message_id={dispatch_res.message_id}）")
        logger.info("[Worker] 开始执行 Background Agent Loop...")

        await run_agent_background(thread_id, dispatch_res.inputs)

        elapsed = time.time() - start_time
        logger.info("=" * 60)
        logger.info(f"✅ [Worker] A2A 任务执行完成，总耗时：{elapsed:.2f}s")
        logger.info("=" * 60)

        # 打印消息历史
        from sqlalchemy import select
        from app.models import Message

        async with session_scope() as session:
            stmt = (
                select(Message)
                .where(Message.thread_id == thread_id)
                .order_by(Message.sequence_number)
            )
            res = await session.execute(stmt)
            all_msgs = res.scalars().all()

            logger.info(f"[Worker] 总消息数：{len(all_msgs)}")
            for m in all_msgs:
                icon = "👤" if m.role == "human" else "🤖" if m.role == "ai" else "🛠️"
                preview = str(m.content or "")[:400]
                logger.info(
                    f"{icon} [{m.sequence_number}] {m.role.upper()} "
                    f"({m.action_type}/{m.category}):\n{preview}\n{'-' * 40}"
                )

    finally:
        await db_resource_manager.shutdown()
        logger.info("--- [Worker] 清理完成 ---")


if __name__ == "__main__":
    asyncio.run(run_verification())
