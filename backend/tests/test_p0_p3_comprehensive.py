import asyncio
import logging
import os
import sys
import json
from unittest.mock import patch, MagicMock

# Load env before imports
from dotenv import load_dotenv
load_dotenv()

# Add backend path to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_p0_p3")

# Import reasoning to apply the monkey-patch for Kimi
import app.core.engine.message.reasoning

from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.state import AgentState, BlackboardState, StateUpdate
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

# Mocking constants
TOKEN = "MDAwMDAwMDAwMJmvg62RumKdio-wnJO4tM6DoKfUf9OvrL2KfpO-jpthlY1qpYDNoKx-sclpf9u4lYJ6r5aCqaufyHt608eluJeYfaWtkbZ6an2LyWmA27jegrCr24W-kXA"

async def mock_async_none(*args, **kwargs):
    return None

async def run_scenario(name: str, input_text: str):
    print("\n" + "="*80)
    print(f"SCENARIO: {name} | Input: '{input_text}'")
    print("="*80)

    # 1. Mocks
    mock_db = MagicMock()
    mock_db.checkpointer = MemorySaver()
    
    mock_activity = MagicMock()
    mock_activity.update_agent_state = MagicMock(side_effect=mock_async_none)
    mock_activity.check_cancellation = MagicMock(side_effect=mock_async_none)

    # Mock i18n
    mock_i18n = MagicMock()
    mock_i18n.get = MagicMock(side_effect=lambda key, **kwargs: key)

    # Mock tool_manager
    from app.core.engine.tools.orchestration.routing import route_to
    from app.domain.tools.files.read_file import read_file
    from app.core.engine.tools.orchestration.planning import decompose_task
    
    async def mock_get_node_tools(node_id, state):
        if node_id == "supervisor":
            return [route_to, decompose_task]
        if node_id == "worker":
            return [read_file]
        return []

    # Apply patches
    with patch("app.infrastructure.database.resource_manager.db_resource_manager", mock_db), \
         patch("app.core.evocloud.evocloud_manager.get_token", return_value=TOKEN), \
         patch("app.core.monitoring.activity.activity_monitor", mock_activity), \
         patch("app.i18n.service.i18n", mock_i18n), \
         patch("app.core.tools.manager.tool_manager.get_node_tools", side_effect=mock_get_node_tools), \
         patch("app.core.engine.skill_hydrator.SkillHydrator.get_node_skills", return_value=[]), \
         patch("app.core.engine.context_hydrator.EvoContextMiddleware.hydrate", side_effect=lambda s, c: s):

        # 2. Build Graph
        builder = GraphBuilder()
        config_path = os.path.join(os.path.dirname(__file__), "app/core/engine/config/agent_main.yaml")
        graph = builder.build(config_path, checkpointer=mock_db.checkpointer)
        
        # 3. Initialize State
        state = AgentState(
            messages=[HumanMessage(content=input_text)],
            blackboard=BlackboardState(),
            session_goal=input_text,
            iteration_count=0
        )
        
        # 4. Setup Config
        config = {
            "configurable": {
                "thread_id": f"scenario_{name.lower().replace(' ', '_')}",
                "model": "kimi-k2-thinking-turbo"
            }
        }
        
        # 5. Run Graph
        async for event in graph.astream(state, config=config, stream_mode="values"):
            if event and "messages" in event and event["messages"]:
                last_msg = event["messages"][-1]
                
                # Identify node
                node = "unknown"
                if hasattr(last_msg, "additional_kwargs"):
                    node = last_msg.additional_kwargs.get("node_source", "unknown")
                
                content = getattr(last_msg, "content", "")
                print(f"[{node}] {type(last_msg).__name__}: {str(content)[:100]}...")
                
                # P0 Verification: Check if technical logs appear in final message
                if node == "finish" and "audit complete" in str(content).lower():
                    print("❌ ERROR: Technical audit log leaked to UI!")
                elif node == "finish":
                    print("✅ P0/P3 PASS: Technical logs suppressed.")

    print(f"SCENARIO {name} COMPLETED")

async def main():
    # Scenario 1: Simple Greeting (P1 Verification)
    await run_scenario("Greeting", "你好")
    
    # Scenario 2: Meta Question (P1 Verification)
    await run_scenario("Capabilities", "你能帮我做什么？")
    
    # Scenario 3: Task Decomposition (P2 & Loop Verification)
    await run_scenario("Decomposition", "分两步分析这个项目，第一步读 pyproject.toml，第二步读 README.md")

if __name__ == "__main__":
    asyncio.run(main())
