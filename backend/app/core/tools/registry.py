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
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import yaml
from langchain_core.tools import BaseTool

from app.core.tools.runtime_registry import get_runtime_tools

logger = logging.getLogger(__name__)

# Default YAML config path
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "engine" / "config" / "agent_main.yaml"


# --- Fallback Metadata for System/External Tools ---
# Used for tools that are not decorated with @evoloop_tool or are external (MCP/Built-in)
SYSTEM_TOOL_METADATA = {
    "execute_command": {
        "summary_template": "database_logger.tool_summary.execute_command",
        "is_state_mutating": True,
        "name_map": {"zh": "执行命令", "en": "Execute Command"},
    },
    "task_boundary": {
        "summary_template": "database_logger.tool_summary.task_boundary",
        "is_pollable": True,
        "name_map": {"zh": "任务边界", "en": "Task Boundary"},
    },
    "write_to_file": {
        "summary_template": "database_logger.tool_summary.write_file",
        "affected_path_keys": ["TargetFile"],
        "is_state_mutating": True,
        "name_map": {"zh": "写入文件", "en": "Write File"},
    },
    "replace_file_content": {
        "summary_template": "database_logger.tool_summary.edit_file",
        "affected_path_keys": ["TargetFile"],
        "is_state_mutating": True,
        "name_map": {"zh": "替换文件内容", "en": "Replace File Content"},
    },
    "multi_replace_file_content": {
        "summary_template": "database_logger.tool_summary.edit_file",
        "affected_path_keys": ["TargetFile"],
        "is_state_mutating": True,
        "name_map": {"zh": "批量替换文件", "en": "Multi-Replace File"},
    },
}


class AutoDiscoveryRegistry:
    """
    Registry that automatically scans packages for tools marked with @evoloop_tool.
    """

    def __init__(self):
        self._tools: list[BaseTool] = []
        self._scanned_packages = set()

    def register(self, tool: BaseTool):
        """
        Manually register a tool.
        """
        if tool not in self._tools:
            self._tools.append(tool)
            logger.debug(f"Manually registered tool: {tool.name}")

            # Invalidate global cache
            global _cached_tool_map
            _cached_tool_map = None

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
            logger.error(f"Failed to import package {package_name}: {e}")
            return

        self._scanned_packages.add(package_name)

        # Walk through all modules in the package
        if hasattr(package, "__path__"):
            for _, name, _ispkg in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
                try:
                    module = importlib.import_module(name)
                    self._register_tools_from_module(module)
                except Exception as e:
                    # Log but don't crash on individual module import failures
                    logger.debug(f"Skipping module {name} during scan: {e}")
        else:
            # It's a single module
            self._register_tools_from_module(package)

    def _register_tools_from_module(self, module):
        """
        Inspect a module for @evoloop_tool decorated functions.
        """
        for name, obj in inspect.getmembers(module):
            if isinstance(obj, BaseTool):
                try:
                    wrapped_func = getattr(obj, "func", None) or getattr(obj, "coroutine", None)
                    if wrapped_func and getattr(wrapped_func, "is_evoloop_active", False):
                        if obj not in self._tools:
                            self._tools.append(obj)
                            logger.debug(f"Registered tool: {obj.name} from {module.__name__}")

                            # Invalidate global cache
                            global _cached_tool_map
                            _cached_tool_map = None
                except Exception as e:
                    logger.warning(f"Failed to inspect tool {name} in {module.__name__}: {e}")

    def get_all_tools(self) -> list[BaseTool]:
        """Return all registered tools."""
        _ensure_scanned()
        return list(self._tools)


# --- Initialization ---

REGISTRY = AutoDiscoveryRegistry()


_registry_scanned = False


def _ensure_scanned():
    """Ensure the registry has scanned all packages."""
    global _registry_scanned
    if not _registry_scanned:
        _registry_scanned = True
        # Scan all domain-specific application logic for @evoloop_tool
        REGISTRY.scan("app.domain")

        # Scan Engine Tools (Dynamic Planning)
        REGISTRY.scan("app.core.engine.tools")


# --- Core Registry Accessors ---

_cached_tool_map: dict[str, BaseTool] | None = None
_cached_node_tools: dict[str, list[BaseTool]] = {}  # Cache for role-level hydration


def clear_registry_cache():
    """Clear all internal caches (e.g. after dynamic skill import)."""
    global _cached_tool_map
    _cached_tool_map = None
    _cached_node_tools.clear()
    _load_yaml_config.cache_clear()


def get_tool_map() -> dict[str, BaseTool]:
    """Return a cached mapping of tool names to objects."""
    global _cached_tool_map
    if _cached_tool_map is None:
        _ensure_scanned()
        all_available = REGISTRY.get_all_tools() + get_runtime_tools()
        _cached_tool_map = {t.name: t for t in all_available if t.name}
    return _cached_tool_map


def get_all_tools() -> list[BaseTool]:
    """
    Return a list of all natively available python tools (Static + Runtime).
    WARNING: Does NOT include MCP tools. Use ToolManager for that.
    """
    return list(get_tool_map().values())


def get_tools_by_names(
    tool_names: list[str],
    source_role: str | None = None,
) -> list[BaseTool]:
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
        role_label = source_role or "unknown"
        _report_missing_tools(role_label, missing_tools)

    return hydrated_tools


# --- YAML-Driven Tool Configuration ---

@lru_cache(maxsize=1)
def _load_yaml_config(config_path: str | None = None) -> dict:
    """Load and cache the YAML config for tool-role mappings."""
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error(f"YAML config not found: {path}")
        return {}
    except Exception as e:
        logger.error(f"Failed to parse YAML config {path}: {e}")
        return {}


def _report_missing_tools(node_role: str, missing_tools: list[str]):
    """Report missing tools via logger and activity monitor."""
    logger.error(
        f"[ToolRBAC] Missing tools for role '{node_role}': {missing_tools}. "
        f"These tools are declared in YAML but not found in Registry or MCP."
    )

    loop = asyncio.get_running_loop()
    if not loop.is_running():
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

    # Cache if using default config
    if not config_path:
        _cached_node_tools[node_role] = hydrated

    return hydrated


# --- Convenience Accessors ---


def get_supervisor_tools() -> list[BaseTool]:
    """Return tools for the Supervisor agent."""
    from app.core.tools.manager import tool_manager
    return tool_manager.get_node_tools("supervisor")


# --- Utility Functions ---

def is_state_mutating_tool(tool_name: str) -> bool:
    """Return True if the tool mutates state and should bypass strict dedup."""
    tool_map = get_tool_map()
    if tool_name not in tool_map:
        return False
    # Check custom EvoLoop metadata injected via @evoloop_tool(is_state_mutating=True)
    return getattr(tool_map[tool_name], "metadata", {}).get("is_state_mutating", False)


def is_pollable_tool(tool_name: str) -> bool:
    """Return True if the tool is safe to poll repeatedly without causing a dedup error."""
    tool_map = get_tool_map()
    if tool_name not in tool_map:
        return False
    # Check custom EvoLoop metadata injected via @evoloop_tool(is_pollable=True)
    return getattr(tool_map[tool_name], "metadata", {}).get("is_pollable", False)


def get_tool_metadata(tool_name: str) -> dict:
    """Return the metadata for a tool by name, merging with system fallbacks."""
    tool_map = get_tool_map()
    metadata = {}

    if tool_name in tool_map:
        metadata = getattr(tool_map[tool_name], "metadata", {}) or {}

    # Merge with system fallback if missing key metadata
    if tool_name in SYSTEM_TOOL_METADATA:
        fallback = SYSTEM_TOOL_METADATA[tool_name]
        for k, v in fallback.items():
            if k not in metadata or not metadata[k]:
                metadata[k] = v

    return metadata


def get_tool_friendly_name(tool_name: str, lang: str = "zh") -> str | None:
    """
    Get the friendly display name for a tool in the specified language.

    Args:
        tool_name: The internal tool identifier (e.g., "search_web")
        lang: The language code ("zh", "en", etc.)

    Returns:
        The friendly name if found, None otherwise.
    """
    metadata = get_tool_metadata(tool_name)
    name_map = metadata.get("name_map", {})

    # Try requested language first
    if lang in name_map:
        return name_map[lang]

    # Fallback to any available language
    if name_map:
        return next(iter(name_map.values()))

    return None


def get_tool_affected_paths(tool_name: str, tool_args: dict) -> list[str]:
    """Given a tool execution, return a list of file paths it might mutate."""
    snapshot_paths = []
    if not isinstance(tool_args, dict):
        return snapshot_paths

    tool_map = get_tool_map()
    if tool_name in tool_map:
        tool = tool_map[tool_name]
        metadata = getattr(tool, "metadata", {})
        path_keys = metadata.get("affected_path_keys", [])
        
        for key in path_keys:
            val = tool_args.get(key)
            if val and isinstance(val, str):
                snapshot_paths.append(val)
                
    # Legacy fallback removed. 
    # All mutation-sensitive tools MUST use @evoloop_tool(affected_path_keys=[...])
    return snapshot_paths
