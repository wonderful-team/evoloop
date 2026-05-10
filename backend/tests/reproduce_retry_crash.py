import asyncio
import logging
import os
import sys
import uuid
from sqlalchemy import select

# Load env
from dotenv import load_dotenv
load_dotenv()

# Add backend path to sys.path
sys.path.append(os.getcwd())

from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.core.engine.background_agent import run_agent_background, BackgroundAgentInputs
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.database.sql.database import session_scope
from app.models import Message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("reproduce_crash")

async def initialize_system():
    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    await MemoryLifespanManager.ainitialize()
    auto_discover_handlers()
    builder = GraphBuilder()
    config_path = os.path.join(os.getcwd(), "app/core/engine/config/agent_main.yaml")
    graph = builder.build(config_path, checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)

async def reproduce():
    try:
        await initialize_system()
        
        thread_id = f"reproduce-{uuid.uuid4().hex[:6]}"
        logger.info(f"Using thread_id: {thread_id}")

        # 1. Manually set status to 'stopping' to simulate a recent cancellation
        logger.info("Step 1: Setting status to 'stopping'...")
        # We need to create the activity record first
        await activity_monitor.start_run(thread_id, "Reproduction Initial")
        await activity_monitor.stop_run(thread_id)
        
        # Verify status is indeed 'stopping'
        state = await activity_monitor.get_activity(thread_id)
        logger.info(f"Verified initial status: {state.status}")

        # 2. Simulate Background Agent Start (as 'retry_chat' would do)
        logger.info("Step 2: Starting background agent (this should trigger start_run and check_cancellation)...")
        inputs = BackgroundAgentInputs(
            messages=[{"role": "human", "content": "Hello"}],
            goal="Test Reproduction",
            project_id=43,
            model="gpt-4o" # Provide a model to avoid ValueError
        )
        
        try:
            await run_agent_background(thread_id, inputs)
            logger.info("Success: run_agent_background finished (this is UNEXPECTED if it should crash)")
        except Exception as e:
            logger.error(f"REPRODUCED: Caught exception: {type(e).__name__}: {e}")
            
    finally:
        await db_resource_manager.shutdown()

if __name__ == "__main__":
    asyncio.run(reproduce())
