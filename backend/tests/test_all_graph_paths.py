import asyncio
import logging
import os
import sys
import uuid
from unittest.mock import patch, PropertyMock
from sqlalchemy import select

# Load env
from dotenv import load_dotenv
load_dotenv()

# Add backend path to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_all_paths")

from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background, BackgroundAgentInputs
from app.infrastructure.database.sql.database import session_scope
from app.models import Conversation, Message
from app.core.evocloud.backends.http_client import EvoCloudHTTPClient

async def initialize_system():
    logger.info("--- Initializing Real System for Path Coverage Test ---")
    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    await MemoryLifespanManager.ainitialize()
    auto_discover_handlers()
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "app/core/engine/config/agent_main.yaml")
    graph = builder.build(config_path, checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)
    logger.info("--- System Ready ---")

async def run_scenario(name: str, prompt: str, project_id: int = 43, force_inputs: dict = None):
    print(f"\n" + "="*80)
    print(f"SCENARIO: {name}")
    print(f"PROMPT: {prompt}")
    print("="*80)
    
    thread_id = f"path-test-{uuid.uuid4().hex[:6]}"
    
    # Mocks
    TOKEN = "MDAwMDAwMDAwMJmvg62RumKdio-wnJO4tM6DoKfUf9OvrL2KfpO-jpthlY1qpYDNoKx-sclpf9u4lYJ6r5aCqaufyHt608eluJeYfaWtkbZ6an2LyWmA27jegrCr24W-kXA"
    mock_project = {
        "id": project_id,
        "name": "Path Coverage Project",
        "path": os.getcwd()
    }

    with patch("app.core.evocloud.evocloud_manager.get_token", return_value=TOKEN), \
         patch.object(EvoCloudHTTPClient, "root_url", new_callable=PropertyMock, return_value="https://evoloop.develop-assistant.cn"), \
         patch("app.core.evocloud.evocloud_manager.get_project_by_id", return_value=mock_project):
        
        # 1. Dispatch
        dispatch_res = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=prompt,
            project_id=project_id,
            model="kimi-k2-thinking-turbo"
        )
        
        if dispatch_res.status != "queued":
            print(f"❌ Dispatch failed: {dispatch_res.error}")
            return

        inputs = dispatch_res.inputs
        if force_inputs:
            inputs.update(force_inputs)
        
        # 2. Execution
        await run_agent_background(thread_id, inputs)
        
        # 3. Audit
        async with session_scope() as session:
            stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number)
            res = await session.execute(stmt)
            msgs = res.scalars().all()
            print(f"✅ Scenario '{name}' complete. Total messages: {len(msgs)}")
            for m in msgs:
                print(f"   [{m.sequence_number}] {m.role.upper()}: {str(m.content)[:60]}...")

async def run_all_paths():
    try:
        await initialize_system()
        
        # Scenario 1: Path A - Direct Reply (supervisor -> finish)
        await run_scenario("Direct Reply", "你好，简单介绍下你自己。")
        
        # Scenario 2: Path B - Single Tool (supervisor -> worker -> supervisor -> finish)
        await run_scenario("Single Tool", "帮我列出项目根目录下的 pyproject.toml 文件的内容。")
        
        # Scenario 3: Path C - Parallel Subtasks (supervisor -> spawn -> worker x N -> aggregator -> supervisor)
        await run_scenario("Parallel Subtasks", "请同时执行以下两个原子任务：1. 读取 pyproject.toml；2. 列出 app 目录。请确保使用并行子任务模式（decompose_task）。")
        
        # Scenario 4: Path D - Sequential Workflow (supervisor -> sequential_workflow -> supervisor)
        await run_scenario("Sequential Workflow", "我需要一份针对该项目的深度架构审计报告。请先进行目录扫描，然后分析核心配置，最后生成报告。请使用顺序工作流模式执行。")
        
        # Scenario 5: Path E - Chat Fallback (supervisor -> chat -> finish)
        await run_scenario("Chat Fallback", "咱们随便聊聊量子力学吧，不需要查任何文件。")
        
        # Scenario 6: Path F - Resource Limit (Hard Termination)
        # We manually inject a high iteration_count
        await run_scenario("Resource Limit", "帮我执行一个非常复杂的任务。", force_inputs={"iteration_count": 50})

    finally:
        await db_resource_manager.shutdown()
        logger.info("--- Path Coverage Test Cleanup Complete ---")

if __name__ == "__main__":
    asyncio.run(run_all_paths())
