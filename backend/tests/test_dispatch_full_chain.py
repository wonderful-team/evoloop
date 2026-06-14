import asyncio
import logging
import os
import sys
import json
from unittest.mock import patch, MagicMock, AsyncMock

# Load env before imports
from dotenv import load_dotenv
load_dotenv()

# Add backend path to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_dispatch_chain")

# Import necessary components
import app.core.engine.message.reasoning
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.core.context.manager import ContextManager
from app.core.engine.state import AgentState, BlackboardState
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver

# Mocking constants
TOKEN = "MDAwMDAwMDAwMJmvg62RumKdio-wnJO4tM6DoKfUf9OvrL2KfpO-jpthlY1qpYDNoKx-sclpf9u4lYJ6r5aCqaufyHt608eluJeYfaWtkbZ6an2LyWmA27jegrCr24W-kXA"
THREAD_ID = "test-dispatch-thread-001"

async def mock_async_none(*args, **kwargs):
    return None

async def test_full_chain():
    print("\n" + "="*80)
    print("STARTING FULL DISPATCH TO BACKGROUND CHAIN TEST")
    print("="*80)

    # 1. Mocks
    mock_db = MagicMock()
    mock_db.checkpointer = MemorySaver()
    
    mock_activity = MagicMock()
    mock_activity.update_agent_state = MagicMock(side_effect=mock_async_none)
    mock_activity.check_cancellation = MagicMock(side_effect=mock_async_none)
    mock_activity.start_run = MagicMock(side_effect=mock_async_none)
    mock_activity.end_run = MagicMock(side_effect=mock_async_none)

    # Mock i18n
    mock_i18n = MagicMock()
    mock_i18n.get = MagicMock(side_effect=lambda key, **kwargs: key)

    # Mock Evocloud (Project resolving)
    mock_project = {"id": 1, "path": os.getcwd(), "name": "Test Project"}
    
    # Mock Database session for persistence
    class MockSession:
        async def get(self, model, id): return None
        def add(self, obj): pass
        async def flush(self): pass
        async def execute(self, stmt, params=None):
            m = MagicMock()
            m.scalar = MagicMock(return_value=0)
            return m
        async def commit(self): pass
        async def rollback(self): pass
        async def close(self): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

    def mock_session_scope_func():
        return MockSession()
    
    # Correctly mock session_factory as a callable
    mock_db.session_factory = MagicMock(return_value=MockSession())

    # 2. Patching
    with patch("app.infrastructure.database.resource_manager.db_resource_manager", mock_db), \
         patch("app.infrastructure.database.sql.database.db_resource_manager", mock_db), \
         patch("app.core.evocloud.evocloud_manager.get_token", return_value=TOKEN), \
         patch("app.core.evocloud.evocloud_manager.get_project_by_id", new_callable=AsyncMock, return_value=mock_project), \
         patch("app.core.monitoring.activity.activity_monitor", mock_activity), \
         patch("app.i18n.service.i18n", mock_i18n), \
         patch("app.core.engine.dispatch.session_scope", side_effect=mock_session_scope_func), \
         patch("app.core.engine.background_agent.ContextManager.load", side_effect=ContextManager.load), \
         patch("app.core.engine.context_hydrator.AgentContextHydrator.hydrate", side_effect=mock_async_none), \
         patch("app.core.engine.background_agent.get_graph") as mock_get_graph:

        # Prepare Graph Mock
        mock_graph = MagicMock()
        async def mock_astream(*args, **kwargs):
            # Yield at least one event to simulate run
            yield {"messages": [AIMessage(content="Hello from Background Chain Test")]}
        mock_graph.astream = mock_astream
        mock_get_graph.return_value = mock_graph

        # ---------------------------------------------------------
        # Phase 1: Dispatch
        # ---------------------------------------------------------
        print("\n[Phase 1] Calling dispatch_agent_run...")
        result = await dispatch_agent_run(
            thread_id=THREAD_ID,
            message_content="Hello Agent!",
            project_id=1,
            model="kimi-k2-thinking-turbo"
        )
        
        if result.status == "queued":
            print(f"✅ Dispatch Successful. Message ID: {result.message_id}")
        else:
            print(f"❌ Dispatch Failed: {result.error}")
            return

        # ---------------------------------------------------------
        # Phase 2: Verify Persistence (The bug fix check)
        # ---------------------------------------------------------
        print("\n[Phase 2] Verifying Context Persistence...")
        # Clear local contextvar to ensure we are testing the cache load
        from app.core.context.manager import _context_var
        _context_var.set(None)
        
        loaded_ctx = await ContextManager.load(THREAD_ID)
        if loaded_ctx and loaded_ctx.active_model == "kimi-k2-thinking-turbo":
            print(f"✅ Context Persistence PASS. Model recovered: {loaded_ctx.active_model}")
        else:
            actual = loaded_ctx.active_model if loaded_ctx else "None"
            print(f"❌ Context Persistence FAIL. Expected 'kimi-k2-thinking-turbo', got '{actual}'")
            # If this fails, the background agent will use wrong model or fail.

        # ---------------------------------------------------------
        # Phase 3: Background Run
        # ---------------------------------------------------------
        print("\n[Phase 3] Calling run_agent_background...")
        # We need to mock MemoryLifespanManager to avoid DB/Redis init in test
        with patch("app.core.memory.lifespan.MemoryLifespanManager.is_initialized", return_value=True), \
             patch("app.core.memory.lifespan.MemoryLifespanManager.get_container") as mock_container:
            
            mock_mem = MagicMock()
            mock_mem.get_merged_preferences = MagicMock(side_effect=mock_async_none)
            mock_mem.get_project_concepts = MagicMock(side_effect=mock_async_none)
            mock_container.return_value.memory_manager = mock_mem
            
            await run_agent_background(THREAD_ID, result.inputs)
            print("✅ Background execution call completed.")

    print("\n" + "="*80)
    print("FULL CHAIN TEST COMPLETED")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(test_full_chain())
