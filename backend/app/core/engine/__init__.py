"""
AgentEngine - EvoLoop Agent Execution Engine.

Usage:
    from app.core.engine import AgentEngine

    engine = AgentEngine()
    result = await engine.run_node(state, config, system_prompt, tools)

With dependency injection (for testing):
    engine = AgentEngine(llm_factory=mock_llm)
    result = await engine.run_node(...)
"""

from app.core.engine.engine import AgentEngine, get_default_engine
from app.core.engine.message_utils import repair_message_history

__all__ = [
    "AgentEngine",
    "get_default_engine",
    "repair_message_history",
]
