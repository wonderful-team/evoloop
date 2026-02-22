import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.engine import AgentEngine
from app.core.engine.prompts.dynamic_specialist_builder import (
    DynamicSpecialistPromptBuilder,
)
from app.core.engine.state import AgentState
from app.core.environment import get_awakened_state
from app.core.tools.manager import tool_manager

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

        # 1. Hydrate Tools (Progressive Disclosure)
        # The new ToolManager automatically parses the execution_ticket (including agent_config.tools
        # and mcp_servers_required) and securely binds exactly what we need without prompt explosion.
        tools = tool_manager.get_node_tools("dynamic_specialist", state)

        # 2a. Fetch Relevant Skills/Knowledge (JIT Injection - Phase 5)
        # Using the SkillHydrator middleware to handle Eager/Lazy patterns
        from app.core.engine.nodes.utils import SkillHydrator
        relevant_sops = await SkillHydrator.get_node_skills(state, "dynamic_specialist")

        # 2b. Fetch Environmental Knowledge from Awakening System (Brain/Cache)
        awakened_env = get_awakened_state()
        known_packages = {}
        known_macos_apps = {}
        if awakened_env and awakened_env.relevant_concepts:
            # Extract concepts
            for concept in awakened_env.relevant_concepts:
                if concept.name.startswith("android_package:"):
                    parts = concept.name.split(":")
                    if len(parts) >= 2:
                        known_packages[parts[1]] = concept.description
                elif concept.name.startswith("macos_app:"):
                    parts = concept.name.split(":")
                    if len(parts) >= 2:
                        known_macos_apps[parts[1]] = concept.description

        if known_packages:
            logger.info(f"[DynamicSpecialist] 🧠 Loaded {len(known_packages)} Android packages from Brain.")
        if known_macos_apps:
            logger.info(f"[DynamicSpecialist] 🧠 Loaded {len(known_macos_apps)} MacOS apps from Brain.")

        # 3. Construct Prompts (Using Builder)
        # Pass loaded skills and knowledge to the builder
        scratchpad = state.get("scratchpad", {})
        clipboard = scratchpad.get("workspace_clipboard", [])

        prompt_builder = DynamicSpecialistPromptBuilder(
            agent_config,
            execution_ticket,
            skills=relevant_sops,
            known_packages=known_packages,
            known_macos_apps=known_macos_apps,
            clipboard=clipboard
        )
        system_prompt = prompt_builder.build(config)
        mission_msg = prompt_builder.build_mission_message()
        messages = [HumanMessage(content=mission_msg)]

        # 4. Execute (Using AgentEngine)
        # We spawn a mini-engine instance
        try:
            logger.info(f"[DynamicSpecialist] 🚀 Launching '{role_name}' atomic loop...")

            engine_result = await AgentEngine.run_node(
                state={**state, "messages": messages},  # Isolated state (now correctly using graph state)
                config=config,
                system_prompt=system_prompt,
                tools=tools,
                name=f"Dynamic-{role_name}",
                max_steps=settings.DYNAMIC_AGENT_MAX_STEPS,  # Configured limit
            )

            # 5. Extract Result
            # We want to summarize what happened.
            # The 'messages' in engine_result are the isolated conversation.
            # We append the final result to the MAIN graph history.

            last_msg = engine_result["messages"][-1]
            content = ""
            if isinstance(last_msg, AIMessage):
                content = last_msg.content

            tool_history = engine_result.get("tool_history", [])
            logger.info(f"[DynamicSpecialist][{role_name}] Loop finished. Content len: {len(content)}, Tools used: {len(tool_history)}")

            summary = f"**{role_name} Report**:\n{content}\n\n(Tools used: {len(tool_history)})"

            return_state = {
                "messages": [AIMessage(content=summary)],
                "next_node": "supervisor",
            }

            # Intercept MCP Server requests to update execution ticket
            for t_sig in tool_history:
                tool_name = t_sig.split(":")[0] if ":" in t_sig else t_sig
                if tool_name == "use_mcp_server":
                    try:
                        args_json = t_sig.split(":", 1)[1]
                        args = json.loads(args_json)
                        server_name = args.get("server_name")
                        if server_name:
                            req_servers = set(execution_ticket.get("mcp_servers_required", []))
                            req_servers.add(server_name)
                            execution_ticket["mcp_servers_required"] = list(req_servers)
                            return_state["execution_ticket"] = execution_ticket
                            logger.info(f"[DynamicSpecialist] 🔌 Appended MCP server '{server_name}' to execution_ticket.")
                    except Exception as e:
                        logger.error(f"[DynamicSpecialist] Failed to parse use_mcp_server arguments: {e}")

            return return_state

        except Exception as e:
            logger.error(f"[DynamicSpecialist] 💥 Failed: {e}")
            return {
                "messages": [AIMessage(content=f"Dynamic Agent '{role_name}' failed: {e}")],
                "next_node": "supervisor"
            }


# Singleton
dynamic_specialist_node = DynamicSpecialistNode()
