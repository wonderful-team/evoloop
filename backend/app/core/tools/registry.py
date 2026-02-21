"""
Unified Tool Registry — Dynamic Discovery & RBAC.

This module centralizes tool registration, auto-discovery, and role-based access control (RBAC).
It replaces the legacy registry_utils.py and provides a single source of truth for tools.
"""

import importlib
import inspect
import logging
import pkgutil
import yaml
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timezone

from langchain_core.tools import BaseTool

from app.core.tools.runtime_registry import get_runtime_tools
from app.infrastructure.mcp.client import mcp_client_manager

logger = logging.getLogger(__name__)

# Default YAML config path
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "engine" / "config" / "agent_main.yaml"


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
                except Exception as e:
                    logger.warning(f"Failed to inspect tool {name} in {module.__name__}: {e}")

    def get_all_tools(self) -> list[BaseTool]:
        """Return all registered tools."""
        return list(self._tools)


# --- Initialization ---

REGISTRY = AutoDiscoveryRegistry()

# Scan all domain-specific application logic for @evoloop_tool
REGISTRY.scan("app.domain")

# Scan Brain Tools (Memory, Retrieval) in core
REGISTRY.scan("app.core.brain.tools")


# --- Core Registry Accessors ---

def get_all_tools() -> list[BaseTool]:
    """
    Return a list of all available tools in the domain.
    Combines discovered tools with dynamic ones (MCP, Runtime).
    """
    return REGISTRY.get_all_tools() + mcp_client_manager.get_tools() + get_runtime_tools()


def get_tools_by_names(
    tool_names: list[str],
    source_role: str | None = None,
) -> list[BaseTool]:
    """
    Hydrate a list of tool names into actual BaseTool objects.
    Uses AutoDiscoveryRegistry + MCP as lookup sources.
    """
    all_available = get_all_tools()
    tool_map = {t.name: t for t in all_available if t.name}

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
        with open(path, "r") as f:
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

    try:
        from app.core.monitoring.activity import activity_monitor
        activity_monitor.log_event(
            event_type="tool_missing",
            data={
                "node_role": node_role,
                "missing_tools": missing_tools,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "severity": "warning",
            },
        )
    except Exception as e:
        logger.debug(f"Failed to report missing tools to activity monitor: {e}")


def get_node_tools(node_role: str, config_path: str | None = None) -> list[BaseTool]:
    """Get tools for a specific agent node/role from YAML config."""
    config = _load_yaml_config(config_path)
    tool_names: list[str] = []

    # 1. Check graph node declarations first
    for node in config.get("nodes", []):
        if node.get("id") == node_role and node.get("tools"):
            tool_names = node["tools"]
            break

    # 2. If not found in nodes, check role_tools section
    if not tool_names:
        role_tools = config.get("role_tools", {})
        tool_names = role_tools.get(node_role, [])

    if not tool_names:
        logger.warning(f"[ToolRBAC] No tools declared for role '{node_role}' in YAML config.")
        _report_missing_tools(node_role, [f"<no config for role '{node_role}'>"])
        return []

    return get_tools_by_names(tool_names, source_role=node_role)


# --- Convenience Accessors for Key Roles ---

def get_operator_tools() -> list[BaseTool]:
    """Return standard tools for the Operator agent."""
    return get_node_tools("operator")


def get_supervisor_tools() -> list[BaseTool]:
    """Return tools for the Supervisor agent."""
    tool_names = [
        "save_preference",
        "search_concepts",
        "request_human_input",
        "analyze_image",
        "manage_todo",
    ]
    return get_tools_by_names(tool_names, source_role="supervisor")


# --- Utility Functions ---

def is_state_mutating_tool(tool_name: str) -> bool:
    """Return True if the tool mutates state and should bypass strict dedup."""
    mutating = {
        "write_file", "edit_file", "manage_file", "file_system",
        "write_document", "edit_document", "write_wiki_page",
        "sql_query",
    }
    return tool_name in mutating


def is_pollable_tool(tool_name: str) -> bool:
    """Return True if the tool is safe to poll repeatedly without causing a dedup error."""
    pollable = {
        "wait", "list_files", "search_web", "read_file", "find_element", "request_approval",
    }
    return tool_name in pollable


def get_tool_affected_paths(tool_name: str, tool_args: dict) -> list[str]:
    """Given a tool execution, return a list of file paths it might mutate."""
    snapshot_paths = []
    if not isinstance(tool_args, dict):
        return snapshot_paths

    if tool_name in ["write_file", "edit_file", "write_document", "edit_document"]:
        arg_path = tool_args.get("path")
        if arg_path:
            snapshot_paths.append(arg_path)
    elif tool_name == "manage_file":
        arg_path = tool_args.get("absolute_path") or tool_args.get("path")
        action = tool_args.get("action")
        if arg_path and action in ["create", "update_block", "write", "overwrite", "delete"]:
            snapshot_paths.append(arg_path)
    elif tool_name == "file_system":
        arg_path = tool_args.get("path")
        dest_path = tool_args.get("destination")
        action = tool_args.get("action")
        if arg_path:
            snapshot_paths.append(arg_path)
        if action == "move" and dest_path:
            snapshot_paths.append(dest_path)

    return snapshot_paths
