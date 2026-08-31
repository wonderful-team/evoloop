import logging

from app.core.engine.state import AgentState
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

    async def get_agent_tools(self, agent: str, state: AgentState | None = None) -> list[BaseTool]:
        """
        Get tools for a specific agent role, handling Progressive Disclosure automatically.
        Nodes no longer need to manually parse tickets or talk to MCP.
        """
        from app.core.mcp import mcp_client_manager
        from app.core.tools.registry import get_node_tools

        # 1. Fetch statically configured tools for this role (Native + specifically requested MCP if defined in yaml)
        try:
            tools = get_node_tools(node_name)
        except (TypeError, ValueError, RuntimeError, OSError) as e:
            logger.exception(
                f"[ToolManager] Failed to fetch static tools for {agent}: {e}"
            )
            tools = []

        combined_map = {t.name: t for t in tools if t.name}

        requested_servers: list = []
        all_requested_tools: set = set()

        # 2. Filter out multimodal tools if no vision model is configured
        from app.infrastructure.config.service import SystemConfigService

        vision_configured = SystemConfigService.get_value("VISION_MODEL") is not None
        if not vision_configured:
            multimodal_tools = [
                t.name for t in combined_map.values() if t.metadata.get("is_multimodal")
            ]
            if multimodal_tools:
                logger.info(
                    f"[ToolManager] VISION_MODEL not configured, filtering out multimodal tools: {multimodal_tools}"
                )
                combined_map = {
                    k: v
                    for k, v in combined_map.items()
                    if not v.metadata.get("is_multimodal")
                }

        # 2. Handle Progressive Disclosure (Skill-Tool Handshake & Dynamic Requests)
        # Only inject external tools if explicitly requested by the state.
        if state:
            execution_ticket = state.ticket

            # Agent Config for Dynamic Specialist
            agent_config = execution_ticket.agent_config if execution_ticket else None
            requested_servers = (
                execution_ticket.mcp_servers_required if execution_ticket else []
            )
            dynamic_tools = agent_config.tools if agent_config else []

            # Dynamically requested individual tools come from agent_config.tools
            all_requested_tools = set(dynamic_tools)

            if requested_servers or all_requested_tools:
                try:
                    # We need to run get_tools synchronously, or rather, it assumes
                    # mcp_client_manager.get_tools() which returns cached tools is sufficient
                    # if ensure_connected was called previously (e.g. by `use_mcp_server`).

                    # Use aget_all_tools() to ensure connections are alive before returning cached tools
                    # 先确保 requested MCP server 已连接（Worker 需要用到）
                    from app.core.mcp import mcp_client_manager as _mcp

                    for _s in requested_servers:
                        try:
                            await _mcp.ensure_connected(_s)
                        except Exception as _e:
                            logger.exception(
                                f"[ToolManager] 连接 MCP server {_s} 失败: {_e}"
                            )
                    all_mcp = await mcp_client_manager.aget_all_tools()

                    # Filter for only what was requested to protect context
                    for t in all_mcp:
                        if t.name in combined_map:
                            continue

                        add_tool = False

                        # 1. Is its server explicitly requested?
                        parsed = parse_mcp_tool_name(t.name)
                        if parsed:
                            # 规范化比较（DB 名可能带连字符，parse 后为下划线）
                            norm = re.sub(r"[^a-zA-Z0-9_]", "_", parsed[0]).lower()
                            if parsed[0] in requested_servers or norm in [
                                re.sub(r"[^a-zA-Z0-9_]", "_", s).lower()
                                for s in requested_servers
                            ]:
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
                    logger.exception(
                        f"[ToolManager] Failed to progressively load MCP tools: {e}"
                    )

            elif not all_requested_tools:
                # MCP 是全局基础设施：无显式请求时默认注入所有已连接的全局
                # MCP 工具（值守等场景只管用、不负责加载）。显式 allowlist
                # （all_requested_tools）存在时不走此分支，避免越过白名单。
                try:
                    from app.core.mcp import mcp_client_manager

                    all_mcp = await mcp_client_manager.aget_all_tools()
                    for t in all_mcp:
                        if t.name in combined_map:
                            continue
                        combined_map[t.name] = t
                except (TypeError, ValueError, RuntimeError, OSError) as e:
                    logger.exception(
                        f"[ToolManager] Failed to inject default MCP tools: {e}"
                    )

        if not combined_map:
            logger.warning(
                f"[ToolManager] get_node_tools('{node_name}') resolved to an empty tool list; "
                "agent node will run without tool capabilities. "
                f"requested_servers={requested_servers}, requested_tools={all_requested_tools}"
            )
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
            + "\n".join(mcp_inventory)
            + "\n\n"
            "Note: To access tools from an inactive server, call `use_mcp_server(server_name)`. "
            "The tools will be injected on your next turn.\n"
        )


tool_manager = ToolManager()
