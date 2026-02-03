import logging
from typing import Any

from app.core.config import settings
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine import AgentEngine

from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory
from app.core.prompts.dynamic_specialist_builder import DynamicSpecialistPromptBuilder
from app.core.tools.registry_utils import get_tools_by_names
from app.infrastructure.mcp.client import mcp_client_manager
from app.domain.tools.vector_store import pg_tool_retriever

logger = logging.getLogger(__name__)


class DynamicSpecialistNode:
    """
    The Chameleon Node (v4.0).
    
    This node doesn't have a fixed personality. 
    It hydrates a temporary Agent at runtime based on the `agent_config` 
    found in the ExecutionTicket.
    """

    async def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        execution_ticket = state.get("execution_ticket")
        
        if not execution_ticket or not execution_ticket.get("agent_config"):
            logger.error("[DynamicSpecialist] No AgentConfig found in ticket! Aborting.")
            return {
                "messages": [AIMessage(content="Error: I was summoned but given no instructions (missing AgentConfig).")],
                "next_node": "supervisor"
            }

        agent_config = execution_ticket["agent_config"]
        role_name = agent_config.get("role_name", "Specialist")
        instructions = agent_config.get("system_instructions", "You are a helpful assistant.")
        tool_names = agent_config.get("tools", [])
        
        logger.info(f"[DynamicSpecialist] 🦎 Hydrating as '{role_name}' with tools: {tool_names}")

        # 1. Hydrate Tools
        # We need to fetch the actual tool objects from registry
        # A. Static Tools
        tools = get_tools_by_names(tool_names)
        
        # B. Verify all tools were found
        found_names = {t.name for t in tools}
        missing = set(tool_names) - found_names
        if missing:
            logger.warning(f"[DynamicSpecialist] ⚠️ Could not find tools: {missing}. Checking MCP/RAG...")
            # Fallback: check MCP
            mcp_tools = mcp_client_manager.get_tools()
            for t in mcp_tools:
                if t.name in missing:
                    tools.append(t)
                    found_names.add(t.name)
            
            # Re-check
            still_missing = set(tool_names) - found_names
            if still_missing:
                 logger.error(f"[DynamicSpecialist] ❌ Definitively missing tools: {still_missing}")
                 # We proceed without them, but warn.

        # 2. Construct Prompts (Using Builder)
        prompt_builder = DynamicSpecialistPromptBuilder(agent_config, execution_ticket)
        system_prompt = prompt_builder.build(config)
        mission_msg = prompt_builder.build_mission_message()
        
        messages = [HumanMessage(content=mission_msg)]

        # 4. Execute (Using AgentEngine)
        # We spawn a mini-engine instance
        try:
            logger.info(f"[DynamicSpecialist] 🚀 Launching '{role_name}' atomic loop...")
            
            engine_result = await AgentEngine.run_node(
                state={**state, "messages": messages}, # Isolated state
                config=config,
                system_prompt=system_prompt,
                tools=tools,
                name=f"Dynamic-{role_name}",
                max_steps=settings.DYNAMIC_AGENT_MAX_STEPS, # Configured limit
            )
            
            # 5. Extract Result
            # We want to summarize what happened. 
            # The 'messages' in engine_result are the isolated conversation.
            # We append the final result to the MAIN graph history.
            
            last_msg = engine_result["messages"][-1]
            content = ""
            if isinstance(last_msg, AIMessage):
                content = last_msg.content
            
            # Verify if tools ran
            tool_history = engine_result.get("tool_history", [])
            
            summary = f"**{role_name} Report**:\n{content}\n\n(Tools used: {len(tool_history)})"
            
            return {
                "messages": [AIMessage(content=summary)],
                "next_node": "supervisor",
                # We can also populate structured results if needed
            }

        except Exception as e:
            logger.error(f"[DynamicSpecialist] 💥 Failed: {e}")
            return {
                "messages": [AIMessage(content=f"Dynamic Agent '{role_name}' failed: {e}")],
                "next_node": "supervisor"
            }


# Singleton
dynamic_specialist_node = DynamicSpecialistNode()
