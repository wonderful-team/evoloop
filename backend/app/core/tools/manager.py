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
        from app.core.tools.registry import get_agent_tools

        # 1. Fetch statically configured tools for this role (Native + specifically requested MCP if defined in yaml)
        try:
            tools = get_agent_tools(agent)
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

        # 2. Inject connected global MCP tools
        # react 单 Agent 架构下工具面由 agent_main.yaml 决定，MCP 工具作为全局基础设施
        # 默认注入（use_mcp_server 工具负责连接管理）。
        if state:
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
                f"[ToolManager] get_agent_tools('{agent}') resolved to an empty tool list; "
                "agent node will run without tool capabilities. "
                f"requested_servers={requested_servers}, requested_tools={all_requested_tools}"
            )
        return list(combined_map.values())

    async def get_all_capabilities(self) -> list[BaseTool]:
        """
        Global dictionary of all tools (NATIVE + CONNECTED MCP).
        WARNING: Do NOT use this to build Prompts (Prompt Explosion).
        Used purely for tool-search / capability-lookup (Atlas、工具管理 UI)。
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
