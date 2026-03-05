import logging

from langchain_core.tools import BaseTool

from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)


class ToolManager:
    """
    Unified ToolBox (v4.0 Architecture).
    
    Serves as the single facade for all Agent Nodes to request tools.
    Encapsulates:
    1. Static Tool Discovery (@evoloop_tool)
    2. Runtime Native Tools
    3. Role-Based Access Control (agent_main.yaml)
    4. Progressive Disclosure (Dynamic MCP loading)
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_node_tools(self, node_name: str, state: AgentState | None = None) -> list[BaseTool]:
        """
        Get tools for a specific agent role, handling Progressive Disclosure automatically.
        Nodes no longer need to manually parse execution_tickets or talk to MCP.
        """
        from app.core.tools.mcp.client import mcp_client_manager
        from app.core.tools.registry import get_node_tools as _legacy_get_node_tools

        # 1. Fetch statically configured tools for this role (Native + specifically requested MCP if defined in yaml)
        try:
            tools = _legacy_get_node_tools(node_name)
        except Exception as e:
            logger.error(f"[ToolManager] Failed to fetch static tools for {node_name}: {e}")
            tools = []

        combined_map = {t.name: t for t in tools if t.name}

        # 2. Handle Progressive Disclosure (Skill-Tool Handshake & Dynamic Requests)
        # Only inject external tools if explicitly requested by the state.
        if state:
            execution_ticket = state.get("execution_ticket") or {}
            requested_servers = execution_ticket.get("mcp_servers_required", [])
            requested_tools = execution_ticket.get("tools_used", [])

            # Agent Config for Dynamic Specialist
            agent_config = execution_ticket.get("agent_config", {})
            dynamic_tools = agent_config.get("tools", [])

            # Merge dynamically requested individual tools
            all_requested_tools = set(requested_tools + dynamic_tools)

            if requested_servers or all_requested_tools:
                try:

                    # We need to run get_tools_for synchronously, or rather, it assumes
                    # mcp_client_manager.get_tools() which returns cached tools is sufficient
                    # if ensure_connected was called previously (e.g. by `use_mcp_server`).

                    # Instead of awaiting here (since get_node_tools in Registry wasn't strictly async initially,
                    # but wait, Operator '_get_tools' was async). Let's fetch from cached tools first.
                    all_mcp = mcp_client_manager.get_tools()

                    # Filter for only what was requested to protect context
                    for t in all_mcp:
                        if t.name in combined_map:
                            continue

                        add_tool = False

                        # 1. Is its server explicitly requested?
                        # Format is usually mcp__{server}__{tool}
                        if t.name.startswith("mcp__"):
                            parts = t.name.split("__")
                            if len(parts) >= 3 and parts[1] in requested_servers:
                                add_tool = True

                        # 2. Is the specific tool explicitly requested?
                        if t.name in all_requested_tools:
                            add_tool = True

                        # Edge case for Dynamic Specialist falling back to ANY tool by string match
                        # (Legacy support for dynamically requesting a tool by its exact name)
                        if t.name in dynamic_tools:
                            add_tool = True

                        if add_tool:
                            combined_map[t.name] = t
                except Exception as e:
                    logger.error(f"[ToolManager] Failed to progressively load MCP tools: {e}")

            # 3. Strict Supervisor Allowlist Enforcement
            if dynamic_tools:
                # If Supervisor provided a strict tool allowlist, we prune any tool not in the list.
                allowed = set(dynamic_tools)
                combined_map = {k: v for k, v in combined_map.items() if k in allowed}

        return list(combined_map.values())

    def get_all_capabilities(self) -> list[BaseTool]:
        """
        Global dictionary of all tools (NATIVE + CONNECTED MCP). 
        WARNING: Do NOT use this to build Prompts (Prompt Explosion).
        Used purely for `search_native_tools` tool-lookup.
        """
        from app.core.tools.mcp.client import mcp_client_manager
        from app.core.tools.registry import get_all_tools as _legacy_get_all_tools

        native_tools = _legacy_get_all_tools()
        mcp_tools = mcp_client_manager.get_tools()

        return list(native_tools) + list(mcp_tools)

    def get_mcp_inventory(self) -> str:
        """
        Build a markdown section listing available and active MCP servers.
        Used by PromptBuilders to give the agent awareness of external plugins.
        """
        from app.core.tools.mcp.client import mcp_client_manager

        mcp_inventory = []
        if hasattr(mcp_client_manager, '_server_configs'):
            for s_name in mcp_client_manager._server_configs.keys():
                is_connected = s_name in mcp_client_manager.sessions
                status = "🟢 Connected" if is_connected else "⚪ Available (Inactive)"
                mcp_inventory.append(f"- **{s_name}** ({status})")

        if not mcp_inventory:
            return ""

        return (
            "### EXTERNAL CAPABILITIES (MCP SERVERS)\n"
            "The following Model Context Protocol (MCP) servers are available to expand your capabilities:\n"
            + "\n".join(mcp_inventory) + "\n\n"
            "⚠️ **CRITICAL: To access tools from an inactive server, you MUST call `use_mcp_server(server_name)`.** "
            "The tools will be injected on your next turn.\n"
        )


tool_manager = ToolManager()
