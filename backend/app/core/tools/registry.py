"""
Unified Tool Registry — Dynamic Discovery & RBAC.

This module centralizes tool registration, auto-discovery, and role-based access control (RBAC).
It replaces the legacy registry_utils.py and provides a single source of truth for tools.
"""

import asyncio
import importlib
import inspect
import logging
import pkgutil
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app.core.tools.base import EvoLoopTool as BaseTool
from app.core.tools.schemas import EvoLoopToolConfig
from app.utils.yaml import load_yaml_file

logger = logging.getLogger(__name__)

# Default YAML config path
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "engine" / "config" / "agent_main.yaml"


class AutoDiscoveryRegistry:
    """
    Registry that automatically scans packages for tools marked with @evoloop_tool.
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._runtime_tools: dict[str, BaseTool] = {}
        self._scanned_packages = set()

    def register(self, tool: BaseTool):
        """Manually register a static tool."""
        self._tools[tool.name] = tool
        logger.debug(f"Manually registered tool: {tool.name}")
        _invalidate_caches()

    def register_runtime(self, tool: BaseTool):
        """Register a dynamically created runtime tool (overrides static by name)."""
        self._runtime_tools[tool.name] = tool
        logger.debug(f"Registered runtime tool: {tool.name}")
        _invalidate_caches()

    def scan(self, package_name: str):
        """
        Recursively scan a package for tools.
        Args:
            package_name: The dotted python path to the package (e.g. "app.domain.tools")
        """
        if package_name in self._scanned_packages:
            return

        try:
            package = importlib.import_module(package_name)
        except ImportError as e:
            logger.exception(f"Failed to import package {package_name}: {e}")
            return

        self._scanned_packages.add(package_name)
        logger.info(f"[Registry] Scanning package: {package_name}")

        # Walk through all modules in the package
        if hasattr(package, "__path__"):
            for _, name, _ispkg in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
                try:
                    module = importlib.import_module(name)
                    self._register_tools_from_module(module)
                except (ImportError, TypeError, ValueError, RuntimeError) as e:
                    # WARNING level so failures are visible in production
                    logger.warning(f"[Registry] Skipping module {name} during scan: {e}", exc_info=True)
        else:
            # It's a single module
            self._register_tools_from_module(package)

    def _register_tools_from_module(self, module):
        """
        Inspect a module for @evoloop_tool decorated functions.
        Batch cache invalidation to avoid repeated cache thrashing.
        """
        new_tools: list[str] = []
        for name, obj in inspect.getmembers(module):
            if isinstance(obj, BaseTool):
                try:
                    wrapped_func = getattr(obj, "func", None) or getattr(obj, "coroutine", None)
                    if wrapped_func and getattr(wrapped_func, "is_evoloop_active", False):
                        if obj.name not in self._tools:
                            self._tools[obj.name] = obj
                            new_tools.append(obj.name)
                            logger.debug(f"Registered tool: {obj.name} from {module.__name__}")
                except (TypeError, ValueError, AttributeError, RuntimeError) as e:
                    logger.warning(f"Failed to inspect tool {name} in {module.__name__}: {e}", exc_info=True)
        if new_tools:
            _invalidate_caches()

    def get_all_tools(self) -> list[BaseTool]:
        """Return all statically registered tools."""
        return list(self._tools.values())

    def get_runtime_tools(self) -> list[BaseTool]:
        """Return all dynamically registered runtime tools."""
        return list(self._runtime_tools.values())

    def get_tool_map(self) -> dict[str, BaseTool]:
        """Return a merged mapping of static + runtime tools (runtime overrides static)."""
        return {**self._tools, **self._runtime_tools}


REGISTRY = AutoDiscoveryRegistry()
_registry_scanned = False
_scan_lock = threading.Lock()


# Critical tools that MUST be present after scanning
_CRITICAL_TOOLS = ["route_to"]


def _validate_critical_tools():
    """Validate that critical tools are registered after scanning. Retry if missing."""
    tool_map = REGISTRY.get_tool_map()
    missing = [t for t in _CRITICAL_TOOLS if t not in tool_map]
    if missing:
        logger.error(f"[Registry] Critical tools missing after scan: {missing}. Retrying engine.tools scan.")
        REGISTRY._scanned_packages.discard("app.core.engine.tools")
        REGISTRY.scan("app.core.engine.tools")

        # Final check
        tool_map = REGISTRY.get_tool_map()
        still_missing = [t for t in _CRITICAL_TOOLS if t not in tool_map]
        if still_missing:
            logger.error(
                f"[Registry] CRITICAL: Tools still missing after retry: {still_missing}"
            )


def _ensure_scanned():
    """Ensure the registry has scanned all packages. Thread-safe with double-checked locking."""
    global _registry_scanned
    if _registry_scanned:
        return

    with _scan_lock:
        # Double-check after acquiring lock
        if _registry_scanned:
            return

        _registry_scanned = True
        logger.info("[Registry] Starting tool discovery scan...")

        # Scan all domain-specific application logic for @evoloop_tool
        REGISTRY.scan("app.domain")

        REGISTRY.scan("app.core.atlas.tools")
        REGISTRY.scan("app.core.engine.tools")
        REGISTRY.scan("app.core.environment.tools")
        REGISTRY.scan("app.core.execution.terminal.tools")
        REGISTRY.scan("app.core.learning.macro.tools")
        REGISTRY.scan("app.core.file.tools")
        REGISTRY.scan("app.core.hitl")
        REGISTRY.scan("app.core.learning.tools")
        REGISTRY.scan("app.core.mcp.tools")
        REGISTRY.scan("app.core.memory.tools")
        REGISTRY.scan("app.core.project.tools")

        # Validate critical tools are present; retry if necessary
        _validate_critical_tools()

        total = len(REGISTRY.get_tool_map())
        logger.info(f"[Registry] Tool discovery complete. {total} tools registered.")


# --- Core Registry Accessors ---

_cached_tool_map: dict[str, BaseTool] | None = None
_cached_node_tools: dict[str, list[BaseTool]] = {}  # Cache for role-level hydration


def _invalidate_caches() -> None:
    """Invalidate all tool lookup caches."""
    global _cached_tool_map
    _cached_tool_map = None
    _cached_node_tools.clear()


def get_tool_map() -> dict[str, BaseTool]:
    """Return a cached mapping of tool names to objects."""
    global _cached_tool_map
    if _cached_tool_map is None:
        _ensure_scanned()
        _cached_tool_map = REGISTRY.get_tool_map()
    return _cached_tool_map


def get_all_tools() -> list[BaseTool]:
    """
    Return a list of all natively available python tools (Static + Runtime).
    WARNING: Does NOT include MCP tools. Use ToolManager for that.
    """
    return list(get_tool_map().values())


def get_tools_by_names(tool_names: list[str], source_role: str | None = None) -> list[BaseTool]:
    """
    Hydrate a list of tool names into actual BaseTool objects.
    Uses AutoDiscoveryRegistry as lookup source. MCP tools are managed by ToolManager.
    """
    tool_map = get_tool_map()

    hydrated_tools: list[BaseTool] = []
    missing_tools: list[str] = []

    for name in tool_names:
        if name in tool_map:
            hydrated_tools.append(tool_map[name])
        else:
            missing_tools.append(name)

    # Strict mode: report missing tools
    if missing_tools:
        _report_missing_tools(source_role, missing_tools)

    return hydrated_tools


# --- YAML-Driven Tool Configuration ---


@lru_cache(maxsize=1)
def _load_yaml_config(config_path: str | None = None) -> dict:
    """Load and cache the YAML config for tool-role mappings."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    data = load_yaml_file(path)
    if not data:
        logger.error("Failed to load YAML config %s", path)
    return data


def _report_missing_tools(node_role: str | None, missing_tools: list[str]):
    """Report missing tools via logger and activity monitor.

    缺失可能是预期行为：yaml 声明是节点能力池，部分工具受运行时门控
    （如 ENABLE_MEMORY=False 禁用的记忆工具）未注册。记 warning 而非
    error，避免把"条件性未注册"误报为配置错误。
    """
    logger.warning(
        f"[ToolRBAC] Missing tools for role '{node_role}': {missing_tools}. "
        f"These tools are declared in YAML but not found in Registry or MCP "
        f"(may be gated by runtime settings)."
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # No running loop, skip async logging

    # We have a running loop, safe to create and schedule the coroutine
    from app.core.monitoring.activity import activity_monitor

    coro = activity_monitor.log_event(
        event_type="tool_missing",
        data={
            "node_role": node_role,
            "missing_tools": missing_tools,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": "warning",
        },
    )
    loop.create_task(coro)


def get_node_tools(node_role: str, config_path: str | None = None) -> list[BaseTool]:
    """Get tools for a specific agent node/role from YAML config."""
    # 0. Check cache first
    if not config_path and node_role in _cached_node_tools:
        return _cached_node_tools[node_role]

    config = _load_yaml_config(config_path)
    tool_names: list[str] = []

    # Check graph node declarations (only source of truth — role_tools removed)
    for node in config.get("nodes", []):
        if node.get("id") == node_role and node.get("tools"):
            tool_names = node["tools"]
            break

    if not tool_names:
        logger.warning(f"[ToolRBAC] No tools declared for node '{node_role}' in YAML config.")
        _report_missing_tools(node_role, [f"<no config for node '{node_role}'>"])
        return []

    hydrated = get_tools_by_names(tool_names, source_role=node_role)

    # 缓存已解析的工具：yaml 声明是节点能力池，可能因运行时门控（如
    # ENABLE_MEMORY=False 禁用的记忆工具）部分未注册——缺失是预期行为，
    # 不因部分缺失而放弃缓存（否则每次调用都重新解析 + 重复告警）。
    # 缺失项仅记一次性 warning；缓存命中后不再走到这里。
    if not config_path:
        missing_count = len(tool_names) - len(hydrated)
        if missing_count:
            logger.warning(
                f"[Registry] {node_role} tools: {missing_count} declared tools not "
                f"registered (gated/disabled), caching {len(hydrated)}"
            )
        if hydrated:
            _cached_node_tools[node_role] = hydrated

    return hydrated


def get_tool_bundle(bundle_name: str, config_path: str | None = None) -> list[str]:
    """Get a named list of tools defined in the tool_bundles section of YAML config."""
    config = _load_yaml_config(config_path)
    return config.get("tool_bundles", {}).get(bundle_name, [])


# --- Utility Functions ---


def is_state_mutating_tool(tool_name: str) -> bool:
    """Return True if the tool mutates state and should bypass strict dedup."""
    tool_map = get_tool_map()
    if tool_name not in tool_map:
        return False
    # Check custom EvoLoop metadata injected via @evoloop_tool(is_state_mutating=True)
    return tool_map[tool_name].metadata.get("is_state_mutating", False)


def get_tool_metadata(tool_name: str) -> EvoLoopToolConfig:
    """Return the metadata for a tool by name."""
    tool_map = get_tool_map()
    metadata: dict = {}

    if tool_name in tool_map:
        metadata = tool_map[tool_name].metadata or {}

    return EvoLoopToolConfig.model_validate(metadata)


def get_tool_affected_paths(tool_name: str, tool_args: dict) -> list[str]:
    """Given a tool execution, return a list of file paths it might mutate."""
    snapshot_paths = []
    if not isinstance(tool_args, dict):
        return snapshot_paths

    tool_map = get_tool_map()
    if tool_name in tool_map:
        tool = tool_map[tool_name]

        # Generic extension point: tools declare their own path extractor
        # (via @evoloop_tool(affected_path_extractor=...)) in their owning module.
        custom_extractor = getattr(tool, "affected_path_extractor", None)
        if custom_extractor is not None:
            try:
                return custom_extractor(tool_args)
            except (TypeError, ValueError, RuntimeError):
                logger.warning(
                    "[registry] custom affected_path_extractor failed for %s, using generic",
                    tool_name,
                    exc_info=True,
                )

        metadata = tool.metadata
        path_keys = metadata.get("affected_path_keys", [])

        for key in path_keys:
            val = tool_args.get(key)
            if val and isinstance(val, str):
                snapshot_paths.append(val)

    # Legacy fallback and robust extraction
    # We check common keys if the tool is state-mutating
    mutating = is_state_mutating_tool(tool_name)

    if not snapshot_paths and mutating:
        for key in ["path", "file_path", "TargetFile"]:
            val = tool_args.get(key)
            if val and isinstance(val, str):
                snapshot_paths.append(val)

    return snapshot_paths
