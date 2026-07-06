import logging

from app.core.engine.state import AgentState
from app.core.mcp.features.base import parse_mcp_tool_name
from app.core.tools.base import EvoLoopTool as BaseTool

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

    async def get_node_tools(self, node_name: str, state: AgentState | None = None) -> list[BaseTool]:
        """
        Get tools for a specific agent role, handling Progressive Disclosure automatically.
        Nodes no longer need to manually parse execution_tickets or talk to MCP.
        """
        from app.core.mcp import mcp_client_manager
        from app.core.tools.registry import get_node_tools

        # 1. Fetch statically configured tools for this role (Native + specifically requested MCP if defined in yaml)
        try:
            tools = get_node_tools(node_name)
        except (TypeError, ValueError, RuntimeError, OSError) as e:
            logger.error(f"[ToolManager] Failed to fetch static tools for {node_name}: {e}")
            tools = []

        combined_map = {t.name: t for t in tools if t.name}

        # 2. Handle Progressive Disclosure (Skill-Tool Handshake & Dynamic Requests)
        # Only inject external tools if explicitly requested by the state.
        if state:
            execution_ticket = state.ticket

            # Agent Config for Dynamic Specialist
            agent_config = execution_ticket.agent_config if execution_ticket else None
            requested_servers = execution_ticket.mcp_servers_required if execution_ticket else []
            dynamic_tools = agent_config.tools if agent_config else []

            # Dynamically requested individual tools come from agent_config.tools
            all_requested_tools = set(dynamic_tools)

            if requested_servers or all_requested_tools:
                try:

                    # We need to run get_tools synchronously, or rather, it assumes
                    # mcp_client_manager.get_tools() which returns cached tools is sufficient
                    # if ensure_connected was called previously (e.g. by `use_mcp_server`).

                    # Use aget_all_tools() to ensure connections are alive before returning cached tools
                    all_mcp = await mcp_client_manager.aget_all_tools()

                    # Filter for only what was requested to protect context
                    for t in all_mcp:
                        if t.name in combined_map:
                            continue

                        add_tool = False

                        # 1. Is its server explicitly requested?
                        parsed = parse_mcp_tool_name(t.name)
                        if parsed and parsed[0] in requested_servers:
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
                except (TypeError, ValueError, RuntimeError, OSError) as e:
                    logger.error(f"[ToolManager] Failed to progressively load MCP tools: {e}")

            # 3. Strict Supervisor Allowlist Enforcement
            # Only apply this to specialists (workers), NEVER to the supervisor itself.
            if dynamic_tools and node_name != "supervisor":
                # If Supervisor provided a strict tool allowlist, we prune any tool not in the list.
                allowed = set(dynamic_tools)
                combined_map = {k: v for k, v in combined_map.items() if k in allowed}

                # 4. Prevent tool-choice ambiguity: when write_wiki_page is explicitly
                #    authorized, remove write_file so the Agent cannot accidentally
                #    bypass the wiki system and write raw files instead.
                if "write_wiki_page" in allowed and "write_file" in combined_map:
                    combined_map.pop("write_file", None)

        return list(combined_map.values())

    async def get_all_capabilities(self) -> list[BaseTool]:
        """
        Global dictionary of all tools (NATIVE + CONNECTED MCP).
        WARNING: Do NOT use this to build Prompts (Prompt Explosion).
        Used purely for `search_native_tools` tool-lookup.
        """
        from app.core.mcp import mcp_client_manager
        from app.core.tools.registry import get_all_tools

        native_tools = get_all_tools()
        mcp_tools = await mcp_client_manager.aget_all_tools()

        return list(native_tools) + list(mcp_tools)

    def get_mcp_inventory(self) -> str:
        """
        Build a markdown section listing available and active MCP servers.
        Used by PromptBuilders to give the agent awareness of external plugins.
        """
        from app.core.mcp import mcp_client_manager

        mcp_inventory = []
        for s_name in mcp_client_manager._configs.keys():
            is_connected = s_name in mcp_client_manager.sessions
            status = "🟢 Connected" if is_connected else "⚪ Available (Inactive)"
            mcp_inventory.append(f"- **{s_name}** ({status})")

        if not mcp_inventory:
            return ""

        return (
            "EXTERNAL CAPABILITIES (MCP SERVERS)\n"
            "The following Model Context Protocol (MCP) servers are available:\n"
            + "\n".join(mcp_inventory) + "\n\n"
            "Note: To access tools from an inactive server, call `use_mcp_server(server_name)`. "
            "The tools will be injected on your next turn.\n"
        )


tool_manager = ToolManager()
