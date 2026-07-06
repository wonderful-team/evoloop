import logging
from typing import Any

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

    async def prepare_state(self, state: AgentState, config: dict) -> StateUpdate | None:
        return None

    async def build_prompt_pair(self, state: AgentState, config: dict) -> tuple[str, str]:
        from app.infrastructure.config.service import SystemConfigService
        agent_name = SystemConfigService.get_value("AGENT_NAME", "EvoLoop")
        agent_company = SystemConfigService.get_value("AGENT_COMPANY", "上海方天画戟信息技术有限公司")
        agent_website = SystemConfigService.get_value("AGENT_WEBSITE", "https://evoloop.cn")
        static_prompt = (
            f"You are {agent_name}, a helpful AI assistant in 'Chat Mode'.\n"
            f"## Agent Identity\n"
            f"- Name: **{agent_name}**\n"
            f"- Developer: {agent_company}\n"
            f"- Official Website: {agent_website}\n"
        )
        return static_prompt, ""

    async def get_tools(self, state: AgentState) -> list[Any]:
        """Memory tools only."""
        return await tool_manager.get_node_tools("chat", state)

    async def _build_fallback_outcome(
        self,
        original_state: AgentState,
        engine_result: EngineResult,
        config: dict,
    ) -> StateUpdate:
        """Chat routes to FINISH so the audit & event lifecycle runs."""
        return StateUpdate(
            messages=engine_result.messages or [],
            next_node=RoutingTarget.FINISH,
        )
