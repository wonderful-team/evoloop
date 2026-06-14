import asyncio
import logging
import os
import sys
import uuid
from sqlalchemy import select
from unittest.mock import patch, PropertyMock, AsyncMock

# Add backend path to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_code_to_prd_skill")

from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.infrastructure.database.sql.database import session_scope
from app.models import Conversation, Message
from app.core.evocloud import evocloud_manager
from app.core.evocloud.backends.http_client import EvoCloudHTTPClient
from app.core.identity import identity_service

async def initialize_system():
    logger.info("--- Initializing Real System for Code to PRD E2E Test ---")
    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    await MemoryLifespanManager.ainitialize()
    auto_discover_handlers()
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "../app/core/engine/config/agent_main.yaml")
    graph = builder.build(os.path.abspath(config_path), checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)
    logger.info("--- System Base Ready ---")

async def run_verification():
    try:
        await initialize_system()
        
        project_id = 99
        thread_id = f"prd-test-{uuid.uuid4().hex[:6]}"
        target_dir = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/mobile/src"
        
        user_input = (
            f"为前端目录 {target_dir} 生成一份完整的 PRD 文档。请调用 code_to_prd 技能进行代码逆向工程分析。"
        )
        
        logger.info("[Test] Initializing EvoCloud Manager...")
        try:
            evocloud_manager.initialize()
        except Exception as e:
            logger.warning(f"[Test] Initialization notice: {e}")

        client = evocloud_manager.api

        logger.info("Using unthrottled local Gateway as test user...")
        TOKEN = "test-token"
        await identity_service.set_token(TOKEN, "test-refresh")
        member_id = 1
        logger.info(f"Login successful. member_id={member_id}")

        mock_project = {
            "id": project_id,
            "name": "Evoloop Mobile Client Analysis",
            "path": target_dir
        }

        with patch("app.core.evocloud.evocloud_manager.get_token", return_value=TOKEN), \
             patch("app.core.identity.identity_service.get_member_id", return_value=member_id), \
             patch.object(EvoCloudHTTPClient, "root_url", new_callable=PropertyMock, return_value="http://127.0.0.1:9001"), \
             patch("app.core.evocloud.evocloud_manager.get_project_by_id", new_callable=AsyncMock, return_value=mock_project):
            
            logger.info("=" * 60)
            logger.info(f"🚀 STARTING VERIFICATION TEST (Thread: {thread_id})")
            logger.info(f"QUERY: {user_input}")
            logger.info("=" * 60)

            # 1. Dispatch
            logger.info("Dispatching agent run (natural language query)...")
            dispatch_res = await dispatch_agent_run(
                thread_id=thread_id,
                message_content=user_input,
                project_id=project_id,
                model="kimi-k2-thinking-turbo"
            )
            
            if dispatch_res.status != "queued":
                logger.error(f"❌ Dispatch failed: {dispatch_res.error}")
                return
            
            logger.info(f"Agent queued successfully. Inputs: {dispatch_res.inputs}")
            
            # 2. Execution
            logger.info("Executing agent background loop...")
            await run_agent_background(thread_id, dispatch_res.inputs)
            
            # 3. Verification Audit
            logger.info("=" * 60)
            logger.info("📊 FINAL EXECUTION AUDIT")
            logger.info("=" * 60)
            
            async with session_scope() as session:
                stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number)
                res = await session.execute(stmt)
                all_msgs = res.scalars().all()
                
                logger.info(f"Total messages recorded in thread: {len(all_msgs)}")
                for m in all_msgs:
                    role_icon = "👤" if m.role == "human" else "🤖" if m.role == "ai" else "🛠️"
                    logger.info(f"{role_icon} [{m.sequence_number}] {m.role.upper()} ({m.action_type}/{m.category}):\n{str(m.content)[:300]}...\n{'-'*40}")
                    
    finally:
        await db_resource_manager.shutdown()
        logger.info("--- Verification Cleanup Complete ---")

if __name__ == "__main__":
    asyncio.run(run_verification())
