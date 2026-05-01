import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.routers import RoutingTarget
from app.core.engine.schemas import EngineResult
from app.core.engine.state import AgentState, StateUpdate
from app.core.tools.manager import tool_manager

logger = logging.getLogger(__name__)


class ChatNode(BaseAgentNode):
    """
    Chat Node - Handles direct user responses and clarifications.
    """

    def __init__(self):
        super().__init__(node_name="Chat", max_steps=3, temperature=0.5)

    async def prepare_state(self, state: AgentState, config: RunnableConfig) -> StateUpdate | None:
        return None

    async def build_prompt_pair(self, state: AgentState, config: RunnableConfig) -> tuple[str, str]:
        static_prompt = "You are EvoLoop Chat. Answer the user's question concisely and helpfully."
        # No dynamic ticket needed for simple chat
        return static_prompt, ""

    async def get_tools(self, state: AgentState) -> list[Any]:
        """Memory tools only."""
        return await tool_manager.get_node_tools("chat", state)

    async def _build_fallback_outcome(
        self,
        original_state: AgentState,
        engine_result: EngineResult,
        config: RunnableConfig,
    ) -> StateUpdate:
        """Chat routes to FINISH so the audit & event lifecycle runs."""
        return StateUpdate(
            messages=engine_result.messages or [],
            next_node=RoutingTarget.FINISH,
        )
