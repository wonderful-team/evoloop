import pytest
pytestmark = pytest.mark.skip(reason="Integration test script - run manually")

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func

# Load env
from dotenv import load_dotenv
load_dotenv()

# Add backend path to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging to be very verbose for the integration test
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_prod_integration")

from app.core.config import settings
from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.infrastructure.database.sql.database import session_scope
from app.models import Conversation, Message
from unittest.mock import patch, PropertyMock, AsyncMock
from app.core.evocloud.backends.http_client import EvoCloudHTTPClient

async def initialize_system():
    logger.info("--- Initializing Real System Resources ---")
    
    # 1. Database & Tables
    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    
    # 2. Memory System
    await MemoryLifespanManager.ainitialize()
    
    # 3. Lifecycle Handlers
    auto_discover_handlers()
    
    # 4. Engine Graph
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "app/core/engine/config/agent_main.yaml")
    graph = builder.build(config_path, checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)
    
    logger.info("--- System Initialization Complete ---")

async def audit_results(thread_id: str):
    logger.info(f"\n--- AUDIT RESULTS FOR THREAD {thread_id} ---")
    async with session_scope() as session:
        # Check Conversation
        conv = await session.get(Conversation, thread_id)
        if conv:
            print(f"✅ Conversation found in DB: ID={conv.id}, Project={conv.project_id}")
        else:
            print(f"❌ Conversation NOT found in DB!")

        # Check Messages
        stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number)
        result = await session.execute(stmt)
        messages = result.scalars().all()
        print(f"✅ Found {len(messages)} messages in DB:")
        for m in messages:
            content_preview = str(m.content)[:80].replace('\n', ' ')
            print(f"   [{m.sequence_number}] {m.role.upper()}: {content_preview}...")

async def run_integration_test():
    try:
        # 1. Startup
        await initialize_system()
        
        project_id = 43
        thread_id = f"prod-test-{uuid.uuid4().hex[:6]}"
        user_input = "帮我看看项目根目录下的 pyproject.toml 文件，总结一下它的核心依赖。"
        
        # 2. Mock Platform Auth & Project Resolution
        TOKEN = "MDAwMDAwMDAwMJmvg62RumKdio-wnJO4tM6DoKfUf9OvrL2KfpO-jpthlY1qpYDNoKx-sclpf9u4lYJ6r5aCqaufyHt608eluJeYfaWtkbZ6an2LyWmA27jegrCr24W-kXA"
        mock_project = {
            "id": project_id,
            "name": "Integration Test Project 43",
            "path": os.getcwd()
        }

        # Mock both the token and the root_url property
        with patch("app.core.evocloud.evocloud_manager.get_token", return_value=TOKEN), \
             patch.object(EvoCloudHTTPClient, "root_url", new_callable=PropertyMock, return_value="https://evoloop.develop-assistant.cn"), \
             patch("app.core.evocloud.evocloud_manager.get_project_by_id", new_callable=AsyncMock, return_value=mock_project):
            # 3. Dispatch (Real Logic, Real DB)
            print(f"\n[Step 1] Dispatching agent run for project {project_id}...")
            dispatch_res = await dispatch_agent_run(
                thread_id=thread_id,
                message_content=user_input,
                project_id=project_id,
                model="kimi-k2-thinking-turbo"
            )
            
            if dispatch_res.status != "queued":
                print(f"❌ Dispatch failed: {dispatch_res.error}")
                return
            
            print(f"✅ Dispatch successful. Message ID: {dispatch_res.message_id}")

            # 4. Background Execution (Real Logic, Real LLM, Real DB)
            print(f"\n[Step 2] Running Background Agent (Real Kimi Gateway)...")
            await run_agent_background(thread_id, dispatch_res.inputs)
            
            # 5. Audit
            await audit_results(thread_id)
        
    finally:
        await db_resource_manager.shutdown()
        logger.info("--- Test Cleanup Complete ---")

if __name__ == "__main__":
    asyncio.run(run_integration_test())
