import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.engine import EngineResult
from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate
from app.core.tools.manager import tool_manager

logger = logging.getLogger(__name__)


class ChatNode(BaseAgentNode):
    """
    Chat Node - Handles direct user responses and clarifications.
    """

    def __init__(self):
        super().__init__(node_name="chat", max_steps=3, temperature=0.5)

    async def prepare_state(self, state: AgentState, config: RunnableConfig) -> StateUpdate | None:
        return None

    async def build_prompt_pair(self, state: AgentState, config: RunnableConfig) -> tuple[str, str]:
        static_prompt = "You are EvoLoop Chat. Answer the user's question concisely and helpfully."
        # No dynamic ticket needed for simple chat
        return static_prompt, ""

    async def get_tools(self, state: AgentState) -> list[Any]:
        """Memory tools only."""
        return await tool_manager.get_node_tools("chat", state)

    async def handle_outcome(self, original_state: AgentState, engine_result: "EngineResult", config: RunnableConfig) -> StateUpdate:
        """Chat node usually ends after one turn."""
        _in_msgs = engine_result.messages or []
        logger.info(f"[MSG-TRACE][chat] handle_outcome engine_result.messages: {len(_in_msgs)} msgs | types={[type(m).__name__ for m in _in_msgs]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in _in_msgs]} | contents={[str(getattr(m,'content',''))[:60] for m in _in_msgs]}")
        result = StateUpdate(
            messages=engine_result.messages or [],
            next_node=RoutingTarget.END
        )
        _out_msgs = result.messages or []
        logger.info(f"[MSG-TRACE][chat] handle_outcome RETURN StateUpdate.messages: {len(_out_msgs)} msgs | types={[type(m).__name__ for m in _out_msgs]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in _out_msgs]}")
        return result
