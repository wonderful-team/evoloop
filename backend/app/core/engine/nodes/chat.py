from typing import Any, Tuple

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage

from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.prompts import ChatPromptBuilder
from app.core.engine.state import AgentState
from app.core.engine.routers import RoutingTarget
from app.core.memory.tools import recall, remember, search_history

# Lightweight tools for Chat Node (memory-related only)
CHAT_TOOLS = [recall, remember, search_history]


class ChatNode(BaseAgentNode):
    """
    Lightweight node for casual conversation with memory support.
    
    Capabilities:
    - Casual chat and Q&A
    - Recall previously remembered information
    - Search conversation history
    - Remember user preferences
    """

    def __init__(self):
        super().__init__(node_name="Chat", max_steps=1, temperature=0.7)

    async def prepare_state(self, state: AgentState, config: RunnableConfig) -> dict[str, Any] | None:
        """
        Strategy: Only handle pure chat for the first message.
        If it's a follow-up, delegate to Supervisor for better task handling.
        """
        messages = state.get("messages", [])
        human_message_count = sum(1 for m in messages if hasattr(m, "type") and m.type == "human")
        
        if human_message_count > 1:
            return {"next_node": RoutingTarget.SUPERVISOR}
        
        return state

    async def build_prompt_pair(self, state: AgentState, config: RunnableConfig) -> Tuple[str, str]:
        """Chat System Prompt is generally static."""
        prompt_builder = ChatPromptBuilder()
        system_prompt = await prompt_builder.build()
        # Chat currently has no per-turn dynamic ticket
        return system_prompt, ""

    async def get_tools(self, state: AgentState) -> list[Any]:
        """Memory tools only."""
        return CHAT_TOOLS

    async def handle_outcome(self, original_state: AgentState, engine_result: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
        """Chat node usually ends after one turn."""
        return {
            "messages": engine_result.get("messages", []),
            "next_node": RoutingTarget.FINISH
        }


# Singleton for graph registration
chat_node_instance = ChatNode()


async def chat_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Function wrapper for LangGraph registration compatibility."""
    return await chat_node_instance(state, config)
