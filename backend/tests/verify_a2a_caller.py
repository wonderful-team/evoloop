"""
verify_a2a_caller.py
====================
A2A 集成测试 — Caller 端验证脚本

用途：
  在 Caller 实例（PORT=20160, EVOLOOP_APP_DATA_DIR=~/.evoloop）的进程中运行。
  登录 EvoCloud，然后发起一个自然语言 A2A 测试任务：
    - Caller 会调用 list_agents 找到在线的 Worker-Server
    - 生成 deploy_info.txt（内容 "Hello Go Gateway"）并作为附件上传
    - 通过 send_agent_task 将部署任务委托给 Worker

运行方式（在 evoloop/backend 目录下）：
  EVOCLOUD_API_URL=http://localhost:8082 \\
  EVOCLOUD_WS_URL=ws://localhost:9001/ws \\
  EVOCLOUD_DEVICE_TYPE=desktop \\
  EVOCLOUD_DEVICE_CAPABILITIES=code_write,code_build \\
  EVOCLOUD_DEVICE_NAME=Caller-MacBook \\
  EVOLOOP_APP_DATA_DIR=/Users/huangjinhuan/.evoloop \\
  PORT=20160 \\
  ./.venv/bin/python tests/verify_a2a_caller.py
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
logger = logging.getLogger("verify_a2a_caller")

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
    logger.info("--- [Caller] 初始化系统（DB / Memory / Graph）---")
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
    logger.info("--- [Caller] 系统初始化完成 ---")


# ─── 登录 ─────────────────────────────────────────────────────────────────────

async def login(username: str = "preterchan", password: str = "hellomylife"):
    logger.info(f"[Caller] 正在登录 EvoCloud（用户：{username}）...")
    try:
        evocloud_manager.initialize()
    except Exception as e:
        logger.warning(f"[Caller] EvoCloud manager 初始化提示：{e}")

    client = evocloud_manager.api
    login_res = await client.login(username, password)
    if not login_res.get("success"):
        raise RuntimeError(f"[Caller] 登录失败：{login_res}")

    token = login_res["token"]
    refresh_token = login_res.get("refresh_token", "")
    await identity_service.set_token(token, refresh_token)
    member_id = await identity_service.get_member_id(token) or 1
    logger.info(f"[Caller] 登录成功。member_id={member_id}")
    return token, member_id


async def fetch_default_model() -> str:
    """
    从 Gateway 拉取可用模型列表，取第一个 evoloop 类型的 LLM 模型作为默认模型。
    这样不依赖本地 SystemConfigService DB 里的 LLM_MODEL 配置。
    """
    client = evocloud_manager.api
    resp = await client.get_llm_models()
    if resp.get("code") != 0:
        raise RuntimeError(f"[Caller] 获取模型列表失败：{resp}")

    models = resp.get("data", {}).get("models", [])
    for m in models:
        if m.get("config_type") == "evoloop" and m.get("model_type") == "llm":
            model_id = m["model_id"]
            logger.info(f"[Caller] 使用 Gateway 下发的默认模型：{model_id} ({m.get('display_name')})") 
            return model_id

    raise RuntimeError(f"[Caller] 没有可用的 evoloop LLM 模型，请在后台配置")


# ─── 主验证逻辑 ───────────────────────────────────────────────────────────────

async def run_verification():
    try:
        await initialize_system()
        await login()

        # 启动 Device Link 以在发送 A2A 任务时携带 Caller 真实的 device_key
        logger.info("[Caller] 正在启动 EvoCloud 链路并建立 WebSocket 连接...")
        await evocloud_manager.start()
        # 等待 WS 连接成功并获得 device_key
        for _ in range(10):
            if evocloud_manager.link and evocloud_manager.link.device_key:
                logger.info(f"[Caller] WebSocket 已连接，获取到 device_key: {evocloud_manager.link.device_key}")
                break
            await asyncio.sleep(1)
        else:
            logger.warning("[Caller] 等待 WebSocket 连接超时，无法获取 device_key，将使用默认值")

        # 唤醒 Agent 环境（加载项目感知、skills 等）
        from app.core.environment import awaken
        await awaken(project_id=0)

        # 从 Gateway 拉取默认模型（绕过本地未配置 LLM_MODEL 的问题）
        default_model = await fetch_default_model()

        thread_id = f"a2a-caller-test-{uuid.uuid4().hex[:8]}"
        logger.info("=" * 60)
        logger.info(f"🚀 [Caller] 启动 A2A 测试（Thread: {thread_id}）")
        logger.info("=" * 60)

        # 给 Caller 的自然语言指令：
        # 1. 找到在线的 server 设备（Worker-Server）
        # 2. 生成测试文本 deploy_info.txt，写入 "Hello Go Gateway"
        # 3. 通过 send_agent_task 把部署任务+附件委托给 Worker
        user_message = (
            "请使用 list_agents 工具查找在线的 server 部署设备，"
            "并把一个测试部署包部署到它上面。"
            "你可以先生成一个叫 deploy_info.txt 的测试文本，写入 Hello Go Gateway，"
            "然后在发送任务时将其作为附件带上。"
        )

        start_time = time.time()
        logger.info(f"[Caller] 用户指令：{user_message}")
        logger.info("[Caller] 正在调度 Agent Run...")

        dispatch_res = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=user_message,
            project_id=0,
            model=default_model,  # 显式传入从 Gateway 拉取的模型
        )

        if dispatch_res.status != "queued":
            logger.error(f"❌ [Caller] Dispatch 失败：{dispatch_res.error}")
            return

        logger.info(f"[Caller] Agent 已排队（message_id={dispatch_res.message_id}）")
        logger.info("[Caller] 开始执行 Background Agent Loop...")

        await run_agent_background(thread_id, dispatch_res.inputs)

        elapsed = time.time() - start_time
        logger.info("=" * 60)
        logger.info(f"✅ [Caller] A2A 测试完成，总耗时：{elapsed:.2f}s")
        logger.info("=" * 60)

        # 打印消息历史
        from sqlalchemy import select
        from app.infrastructure.database.sql.database import session_scope
        from app.models import Message

        async with session_scope() as session:
            stmt = (
                select(Message)
                .where(Message.thread_id == thread_id)
                .order_by(Message.sequence_number)
            )
            res = await session.execute(stmt)
            all_msgs = res.scalars().all()

            logger.info(f"[Caller] 总消息数：{len(all_msgs)}")
            for m in all_msgs:
                icon = "👤" if m.role == "human" else "🤖" if m.role == "ai" else "🛠️"
                preview = str(m.content or "")[:300]
                logger.info(
                    f"{icon} [{m.sequence_number}] {m.role.upper()} "
                    f"({m.action_type}/{m.category}):\n{preview}\n{'-' * 40}"
                )

    finally:
        await evocloud_manager.stop()
        await db_resource_manager.shutdown()
        logger.info("--- [Caller] 清理完成 ---")


if __name__ == "__main__":
    asyncio.run(run_verification())
