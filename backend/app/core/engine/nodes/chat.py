from typing import Any, Tuple

from langchain_core.runnables import RunnableConfig

from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate
from app.core.memory.tools import recall, remember, search_history

# Lightweight tools for Chat Node (memory-related only)
CHAT_TOOLS = [recall, remember, search_history]


class ChatNode(BaseAgentNode):
    """
    Chat Node - Handles direct user responses and clarifications.
    """

    def __init__(self):
        super().__init__(node_name="chat", max_steps=1, temperature=0.5)

    async def prepare_state(self, state: AgentState, config: RunnableConfig) -> StateUpdate | None:
        return None

    async def build_prompt_pair(self, state: AgentState, config: RunnableConfig) -> Tuple[str, str]:
        static_prompt = "You are EvoLoop Chat. Answer the user's question concisely and helpfully."
        # No dynamic ticket needed for simple chat
        return static_prompt, ""

    async def get_tools(self, state: AgentState) -> list[Any]:
        """Memory tools only."""
        return CHAT_TOOLS

    async def handle_outcome(self, original_state: AgentState, engine_result: dict[str, Any], config: RunnableConfig) -> StateUpdate:
        """Chat node usually ends after one turn."""
        return StateUpdate(
            messages=engine_result.get("messages", []),
            next_node=RoutingTarget.FINISH
        )


# Singleton for graph registration
chat_node_instance = ChatNode()


async def chat_node(state: AgentState, config: RunnableConfig) -> StateUpdate:
    """Function wrapper for LangGraph registration compatibility."""
    return await chat_node_instance(state, config)
