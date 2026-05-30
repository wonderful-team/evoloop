import asyncio
import logging
import os
import sys
import uuid
from sqlalchemy import select
from unittest.mock import patch, PropertyMock

# Load env
from dotenv import load_dotenv

from app.core.evocloud import evocloud_manager

load_dotenv()

# Add backend path to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_multi_turn")

from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.infrastructure.database.sql.database import session_scope
from app.models import Conversation, Message
from app.core.evocloud.backends.http_client import EvoCloudHTTPClient

async def initialize_system():
    logger.info("--- Initializing Real System for Multi-Turn Test ---")
    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    await MemoryLifespanManager.ainitialize()
    auto_discover_handlers()
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app/core/engine/config/agent_main.yaml")
    graph = builder.build(config_path, checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)
    logger.info("--- System Ready ---")

async def run_multi_turn_test():
    try:
        await initialize_system()
        
        project_id = 43
        thread_id = f"stress-test-{uuid.uuid4().hex[:6]}"
        
        # Test Script: 12 Turns
        conversation_script = [
            "帮我看看项目根目录下的 pyproject.toml 文件，告诉我它的项目名称是什么？",
            "这个项目主要的生产依赖（dependencies）有哪些？",
            "除了生产依赖，开发环境（dev-dependencies）里还用了哪些工具？",
            "【上下文测试】我前三个问题主要是在问哪个文件？",
            "现在帮我列出 app/core 目录下的所有子目录。",
            "进入 engine 目录，看看里面有哪些核心文件（.py）。",
            "帮我读一下 supervisor.py 的前 30 行内容，看看它的 imports 部分。",
            "【上下文测试】我刚才看的 supervisor.py 是在哪个父目录下的？",
            "【跨度测试】回到最初的话题，pyproject.toml 里对 Python 版本的要求是多少？",
            "根据你目前看到的目录结构和依赖，你觉得这个项目的核心架构是基于什么框架的？",
            "列出 app/models 目录下有哪些模型定义文件？",
            "【总结】综合以上所有对话，帮我写一份简单的项目架构审计报告，涵盖依赖管理、核心组件和数据模型。"
        ]

        client = evocloud_manager.api

        # First perform Login to retrieve the authentic member_id
        logger.info("Attempting to login with provided test credentials to obtain member_id...")
        login_res = await client.login("preterchan", "hellomylife")
        if not login_res.get("success"):
            logger.error(f"Failed to login to identify member ID: {login_res}")
            return

        # Fetch user info to get the actual member_id (because login doesn't return it)
        logger.info("Fetching authentic user info from PHP backend...")
        TOKEN = login_res["token"]
        # TOKEN = "MDAwMDAwMDAwMJmvg62RumKdio-wnJO4tM6DoKfUf9OvrL2KfpO-jpthlY1qpYDNoKx-sclpf9u4lYJ6r5aCqaufyHt608eluJeYfaWtkbZ6an2LyWmA27jegrCr24W-kXA"

        mock_project = {
            "id": project_id,
            "name": "Multi-Turn Stress Project",
            "path": os.getcwd()
        }

        with patch("app.core.evocloud.evocloud_manager.get_token", return_value=TOKEN), \
             patch.object(EvoCloudHTTPClient, "root_url", new_callable=PropertyMock, return_value="https://evoloop.develop-assistant.cn"), \
             patch("app.core.evocloud.evocloud_manager.get_project_by_id", return_value=mock_project):
            
            for i, user_input in enumerate(conversation_script):
                turn_no = i + 1
                print(f"\n" + "!"*40)
                print(f"!!! STARTING TURN {turn_no} / {len(conversation_script)}")
                print(f"!!! USER: {user_input}")
                print("!"*40 + "\n")

                # 1. Dispatch
                dispatch_res = await dispatch_agent_run(
                    thread_id=thread_id,
                    message_content=user_input,
                    project_id=project_id,
                    model="kimi-k2-thinking-turbo"
                )
                
                if dispatch_res.status != "queued":
                    print(f"❌ Dispatch Turn {turn_no} failed: {dispatch_res.error}")
                    break
                
                # 2. Execution
                await run_agent_background(thread_id, dispatch_res.inputs)
                
                # 3. Quick Check
                async with session_scope() as session:
                    stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number.desc()).limit(1)
                    res = await session.execute(stmt)
                    last_msg = res.scalar()
                    if last_msg:
                        print(f"\n✅ Turn {turn_no} Completed. Last AI Response Preview: {str(last_msg.content)[:100]}...")

        # Final Audit
        print(f"\n" + "="*60)
        print(f"FINAL AUDIT FOR MULTI-TURN THREAD: {thread_id}")
        print("="*60)
        async with session_scope() as session:
            stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number)
            res = await session.execute(stmt)
            all_msgs = res.scalars().all()
            print(f"Total messages in conversation history: {len(all_msgs)}")
            for m in all_msgs:
                role_icon = "👤" if m.role == "human" else "🤖" if m.role == "ai" else "🛠️"
                print(f"{role_icon} [{m.sequence_number}] {m.role.upper()}: {str(m.content)[:60]}...")

    finally:
        await db_resource_manager.shutdown()
        logger.info("--- Stress Test Cleanup Complete ---")

if __name__ == "__main__":
    asyncio.run(run_multi_turn_test())
