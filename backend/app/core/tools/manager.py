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

        # 0. 域驱动能力面：按当前会话域解析 capability profile（缺失 = 现状全量）
        profile = self._resolve_domain_profile()

        # 1. Fetch statically configured tools for this role (Native + specifically requested MCP if defined in yaml)
        try:
            tools = get_agent_tools(agent)
        except (TypeError, ValueError, RuntimeError, OSError) as e:
            logger.exception(
                f"[ToolManager] Failed to fetch static tools for {agent}: {e}"
            )
            tools = []

        combined_map = {t.name: t for t in tools if t.name}

        if profile is not None and profile.native_tools is not None:
            allowed_native = set(profile.native_tools)
            combined_map = {
                k: v for k, v in combined_map.items() if k in allowed_native
            }

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
        # react 单 Agent 架构下原生工具面由 agent_main.yaml 决定；MCP 工具可见性
        # 按 capability packages 渐进注入（v2 终态，C3 allowlist 已删）：
        #   预选/加载的包 → (server, tool) 精确面；include 缺省 = server 全量；
        #   无包 = 全量兼容（兜底）。
        if state:
            try:
                from app.core.mcp import mcp_client_manager

                package_surface = await self._resolve_package_surface()
                all_mcp = await mcp_client_manager.aget_all_tools()
                for t in all_mcp:
                    if t.name in combined_map:
                        continue
                    server_name = self._server_of_mcp_tool(t.name).replace("-", "_")
                    if not server_name:
                        continue
                    if package_surface is not None:
                        # 包可见性（预选∪加载合成）：full 优先于 exact——
                        # 同 server 上任一包声明 include 缺省（整 server 全量）
                        # 时，其他包的子集声明不得收窄它；G4 confirm_tools
                        # 被预选排除的写工具不可见
                        exact, full_servers, excluded = package_surface
                        short_name = self._tool_of_mcp_tool(t.name)
                        if server_name in full_servers:
                            pass  # 整 server 全量（excluded 仍生效）
                        elif server_name in exact:
                            if short_name not in exact[server_name]:
                                continue
                        else:
                            continue
                        if short_name in (excluded.get(server_name) or set()):
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
                f"allowed_native={bool(allowed_native)}, package_surface={'set' if package_surface else None}"
            )
        if profile is not None:
            logger.info(
                f"[ToolManager] domain='{profile.domain}' assembled surface: "
                f"native={len([t for t in combined_map.values() if not t.name.startswith('mcp__')])}, "
                f"mcp={len([t for t in combined_map.values() if t.name.startswith('mcp__')])}"
            )
        return list(combined_map.values())

    @staticmethod
    def _resolve_domain_profile():
        """Read the session's resolved domain from ContextManager intent_hint."""
        try:
            from app.core.context import ContextManager
            from app.core.engine.capability_profiles import get_profile

            ctx = ContextManager.current()
            hint = (ctx.metadata or {}).get("intent_hint")
            domain = None
            if hint is not None:
                domain = getattr(hint, "domain", None) or (
                    hint.get("domain") if isinstance(hint, dict) else None
                )
            return get_profile(domain, ctx.working_directory)
        except Exception:
            logger.exception("[ToolManager] domain profile resolution failed")
            return None

    @staticmethod
    def _server_of_mcp_tool(tool_name: str) -> str:
        """mcp__<server>__<tool> → <server>；非 MCP 工具返回空串。"""
        if not tool_name.startswith("mcp__"):
            return ""
        parts = tool_name.split("__")
        return parts[1] if len(parts) > 2 else ""

    @staticmethod
    def _tool_of_mcp_tool(tool_name: str) -> str:
        """mcp__<server>__<tool> → <tool>（短名）；非 MCP 工具返回原名。"""
        if not tool_name.startswith("mcp__"):
            return tool_name
        parts = tool_name.split("__")
        return parts[2] if len(parts) > 2 else tool_name

    async def _resolve_package_surface(
        self,
    ) -> tuple[dict[str, set[str]], set[str], set[str]] | None:
        """解析当前 thread 的包可见性面（capability-packages-refactor.md §6-#5）。

        合成语义：预选集（preselected，每轮重算）∪ 加载集（loaded，thread 级
        叠加）。G4：仅预选包按 ``confirm_tools`` 排除写工具（SOP 未读须显式
        加载包后放开）；已加载包全量 include。

        Returns:
            ``(exact, full_servers, excluded)``：exact 为 ``server→工具短名集``，
            full_servers 为无 include 限制的 server 集，excluded 为被 G4 排除的
            ``server→工具短名集``；无任何包 → None（全量兼容）。
        """
        try:
            from app.core.context import ContextManager
            from app.core.learning.skills.discovery import skill_discovery

            ctx = ContextManager.current()
            metadata = ctx.metadata
            loaded = list(metadata.loaded_packages or [])
            preselected = [
                p for p in (metadata.preselected_packages or []) if p not in loaded
            ]
            if not loaded and not preselected:
                return None

            exact: dict[str, set[str]] = {}
            full_servers: set[str] = set()
            excluded: dict[str, set[str]] = {}

            async def _merge(pkg: str, *, is_preselected: bool) -> None:
                capability = await skill_discovery.get_capability(pkg)
                if not capability:
                    return
                confirm = set(capability.get("confirm_tools") or [])
                for entry in capability.get("tools") or []:
                    server = (entry.get("mcp_server") or "").replace("-", "_")
                    if not server:
                        continue
                    include = entry.get("include")
                    tools = set(include) if isinstance(include, list) and include else None
                    if tools is None:
                        if is_preselected and confirm:
                            excluded.setdefault(server, set()).update(confirm)
                        full_servers.add(server)
                        continue
                    if is_preselected and confirm:
                        excluded.setdefault(server, set()).update(
                            tools & confirm
                        )
                        tools -= confirm
                    if tools:
                        exact.setdefault(server, set()).update(tools)

            for pkg in loaded:
                await _merge(pkg, is_preselected=False)
            for pkg in (metadata.preselected_packages or []):
                if pkg not in loaded:
                    await _merge(pkg, is_preselected=True)

            if not exact and not full_servers:
                # 声明了包但全部失效（被删除/停用）：剔除失效记账，回退全量，
                # 避免幽灵包长期把面锁死在空集。
                if loaded or metadata.preselected_packages:
                    logger.warning(
                        "[ToolManager] all declared packages unresolved (%s); "
                        "falling back to full surface and clearing records",
                        loaded + list(metadata.preselected_packages or []),
                    )
                    metadata.loaded_packages = []
                    metadata.preselected_packages = []
                return None
            return exact, full_servers, excluded
        except Exception:
            logger.exception("[ToolManager] package surface resolution failed")
            return None

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
            "Note: To access tools from an inactive server, load the owning "
            "capability package via `skill(<package_name>)` — its MCP servers "
            "connect automatically on activation.\n"
        )


tool_manager = ToolManager()
