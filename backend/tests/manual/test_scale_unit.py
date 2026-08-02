import os
import sys
import logging
import asyncio
import tempfile

# Setup a temporary app data dir to avoid permission issues with cache
temp_dir = tempfile.mkdtemp()
os.environ["EVOLOOP_APP_DATA_DIR"] = temp_dir
logger = logging.getLogger("test_scale")
logger.info(f"Using temp EVOLOOP_APP_DATA_DIR: {temp_dir}")

# Ensure backend is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

# Mock Blackboard classes before importing ScaleMeasurer
from enum import Enum


class TaskScaleTier(str, Enum):
    TINY = "TINY"
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"

class DynamicBaseModel: # Simple mock
    pass

# We need the real Blackboard models for the test to be valid
from app.core.engine.state.sub_schemas import BlackboardState, BlackboardMetadata
from app.core.engine.state import AgentState
from app.core.engine.nodes.utils.scale_measurer import ScaleMeasurer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_scale")

async def test_scale():
    root = os.getcwd()
    logger.info(f"Scanning: {root}")
    assessment = await ScaleMeasurer.assess(root, session_goal="Build a wiki")
    
    print(f"TIER: {assessment.tier}")
    print(f"FILES: {assessment.metrics.file_count}")
    print(f"STRATEGY: {assessment.recommended_strategy}")
    
    assert assessment.metrics.file_count > 0
    print("✅ ScaleMeasurer Unit Test Passed.")

async def test_worker_integration():
    logger.info("--- Testing WorkerNode integration (Mocked) ---")
    from app.core.engine.nodes.worker import WorkerNode
    from app.core.engine.state.sub_schemas import BlackboardMetadata
    from app.core.engine.state import AgentState
    from app.core.context import ContextManager, EvoContext
    from langchain_core.runnables import RunnableConfig
    
    node = WorkerNode()
    
    # Setup state
    from app.core.engine.state import ExecutionTicket
    ticket = ExecutionTicket(ticket_type="test", topic="test", agent_config={"role_name": "test"})
    blackboard = BlackboardState(ticket=ticket, metadata=BlackboardMetadata())
    state = AgentState(
        project_id=1,
        session_goal="Test goal: Generate wiki",
        blackboard=blackboard,
        messages=[]
    )
    
    # Setup context
    ctx = EvoContext(working_directory=os.getcwd())
    ContextManager.set(ctx)
    
    config: RunnableConfig = {"configurable": {"thread_id": "test_thread"}}
    
    logger.info("Calling prepare_state...")
    await node.prepare_state(state, config)
    
    assessment = state.blackboard.metadata.scale_assessment
    assert assessment is not None
    print(f"Assessment injected: {assessment.tier} ({assessment.metrics.file_count} files)")
    print(f"Budget limit set: {state.blackboard.metadata.budget_limit}")
    
    assert state.blackboard.metadata.budget_limit == 100 # Large project budget
    print("✅ Worker integration test passed.")

async def test_supervisor_prompt():
    logger.info("--- Testing Supervisor Prompt Rendering ---")
    from app.core.engine.nodes.supervisor import SupervisorNode
    from app.core.engine.state.sub_schemas import ScaleAssessment, TaskScaleTier, ScaleMetrics
    from app.core.context import ContextManager, EvoContext
    from langchain_core.runnables import RunnableConfig
    
    # Setup state with assessment
    assessment = ScaleAssessment(
        tier=TaskScaleTier.LARGE,
        metrics=ScaleMetrics(file_count=1234),
        recommended_strategy="PARALLEL",
        reasoning="Test reasoning for large project",
        assessed_at=0
    )
    blackboard = BlackboardState(metadata=BlackboardMetadata(scale_assessment=assessment))
    state = AgentState(
        project_id=1,
        session_goal="Build a giant wiki",
        blackboard=blackboard,
        messages=[]
    )
    
    # Setup context
    ctx = EvoContext(working_directory=os.getcwd())
    ContextManager.set(ctx)
    
    node = SupervisorNode()
    config: RunnableConfig = {"configurable": {"thread_id": "test_thread"}}
    
    static_prompt, dynamic_ticket = await node.build_prompt_pair(state, config)
    
    print("\n--- DYNAMIC TICKET PREVIEW ---")
    print(dynamic_ticket[:1000])
    
    assert "Project Scale**: LARGE" in dynamic_ticket
    assert "Recommended Strategy**: PARALLEL" in dynamic_ticket
    assert "Assessment Reason**: Test reasoning" in dynamic_ticket
    
    print("\n--- STATIC PROMPT PREVIEW ---")
    assert "route_to" in static_prompt
    
    print("✅ Supervisor prompt test passed.")

if __name__ == "__main__":
    asyncio.run(test_scale())
    asyncio.run(test_worker_integration())
    asyncio.run(test_supervisor_prompt())
