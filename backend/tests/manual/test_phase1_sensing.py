import asyncio
import os
import sys
import logging
from typing import Any

# Ensure backend is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from app.core.engine.nodes.utils.scale_measurer import ScaleMeasurer
from app.core.engine.state.sub_schemas import BlackboardState, BlackboardMetadata
from app.core.engine.state import AgentState, ExecutionTicket
from app.core.context import ContextManager, AgentContext

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_phase1")

async def test_scale_measurer():
    logger.info("--- Testing ScaleMeasurer directly ---")
    current_dir = os.getcwd()
    logger.info(f"Scanning current directory: {current_dir}")
    
    assessment = ScaleMeasurer.assess(current_dir, session_goal="Generate a comprehensive wiki for this project.")
    
    logger.info(f"Tier: {assessment.tier}")
    logger.info(f"File Count: {assessment.metrics.file_count}")
    logger.info(f"Recommended Strategy: {assessment.recommended_strategy}")
    logger.info(f"Reasoning: {assessment.reasoning}")
    
    assert assessment.metrics.file_count > 0
    assert assessment.tier in ["SMALL", "MEDIUM", "LARGE"]
    logger.info("✅ ScaleMeasurer test passed.")

async def test_worker_integration():
    logger.info("--- Testing WorkerNode integration (Mocked) ---")
    from app.core.engine.nodes.worker import WorkerNode
    from langchain_core.runnables import RunnableConfig
    
    node = WorkerNode(node_name="test_worker")
    
    # Setup state
    blackboard = BlackboardState(metadata=BlackboardMetadata())
    state = AgentState(
        project_id=1,
        session_goal="Test goal",
        blackboard=blackboard,
        messages=[]
    )
    
    # Setup context
    ctx = AgentContext(working_directory=os.getcwd())
    ContextManager.set(ctx)
    
    config: RunnableConfig = {"configurable": {"thread_id": "test_thread"}}
    
    logger.info("Calling prepare_state...")
    # We don't want to actually run the LLM, just prepare_state
    await node.prepare_state(state, config)
    
    assessment = state.blackboard.metadata.scale_assessment
    assert assessment is not None
    logger.info(f"Assessment injected: {assessment.tier} ({assessment.metrics.file_count} files)")
    logger.info(f"Budget limit set: {state.blackboard.metadata.budget_limit}")
    
    assert state.blackboard.metadata.budget_limit > 0
    logger.info("✅ Worker integration test passed.")

if __name__ == "__main__":
    asyncio.run(test_scale_measurer())
    asyncio.run(test_worker_integration())
