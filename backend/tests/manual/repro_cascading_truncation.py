
import asyncio
import logging
import sys
import os
from typing import Any

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.core.config import settings
from app.core.engine.nodes.worker import WorkerNode
from app.core.engine.nodes.supervisor import SupervisorNode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("repro_cascading_truncation")

async def repro():
    # 1. Initialize Backend
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.core.identity.store import IdentityStore
    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph
    
    logger.info("[Test] Initializing backend...")
    settings.EMBEDDED_MODE = True
    await db_resource_manager.initialize()
    
    # 2. Setup Auth (Internal)
    await IdentityStore.save_access_token("mock-token")
    
    # 2.5 Initialize Graph
    logger.info("[Test] Initializing graph...")
    builder = GraphBuilder()
    config_path = "app/core/engine/config/agent_main.yaml"
    graph = builder.build(config_path)
    set_graph(graph, config_path)
    
    # 3. Force Step Limits
    # Worker limit: 5 steps (enough to do some work but will truncate on wiki generation)
    settings.WORKER_AGENT_MAX_STEPS = 5
    # Supervisor limit: 10 steps
    settings.SUPERVISOR_AGENT_MAX_STEPS = 10
    
    logger.info("Starting Reproduction Test: Cascading Truncation")
    logger.info(f"Worker Max Steps: {settings.WORKER_AGENT_MAX_STEPS}")
    logger.info(f"Supervisor Max Steps: {settings.SUPERVISOR_AGENT_MAX_STEPS}")

    # 2. Setup Project Info
    project_id = 53
    project_path = "/Users/huangjinhuan/项目/testProjects/software-ecommerce"
    
    # 3. Import and run
    from app.core.engine.background_agent import run_agent_background
    
    task = "Generate a comprehensive technical wiki for the software-ecommerce project. Include at least 8 separate pages covering: Overview, Architecture, Database Schema, API Reference, Frontend Structure, Security, Deployment, and Contributing. Use write_wiki_page for each."
    
    thread_id = f"repro-trunc-{int(asyncio.get_event_loop().time())}"
    
    logger.info(f"[Test] Starting agent on thread: {thread_id}")
    
    # Start the background execution
    try:
        # We need to ensure the worker uses the new settings.
        # Since WorkerNode instances might already be created in some factories, 
        # we might need to patch the class or the instances.
        
        inputs = {
            "task": task,
            "model": "kimi-k2-thinking-turbo"
        }
        await run_agent_background(thread_id, inputs)
    except Exception as e:
        logger.error(f"[Test] Agent execution failed: {e}")

if __name__ == "__main__":
    asyncio.run(repro())
