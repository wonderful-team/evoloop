"""
Tool Registry Utilities — YAML-Driven RBAC.

Provides:
  - AutoDiscoveryRegistry: scans packages for @evoloop_tool decorated functions
  - get_node_tools(node_role): loads tool list from YAML config (strict mode, no fallback)
  - get_tools_by_names(names): hydrates tool names to BaseTool objects via registry + MCP
"""

import importlib
import inspect
import logging
import pkgutil
from functools import lru_cache
from pathlib import Path

import yaml
from langchain_core.tools import BaseTool

from app.domain.learning.tools import learn_skill_from_trace
from app.domain.planning.tools import (
    analyze_feasibility,
    create_plan,
    update_step_status,
)
from app.domain.research.tools import search_web
from app.domain.tools.coding.lsp import consult_lsp
from app.domain.tools.facades import (
    consult_architecture,
    edit_document,
    explore_codebase,
    manage_git,
    manage_memory,
    write_document,
)

# Phase 18: New Atomic File Tools
from app.domain.tools.files import (
    edit_file,
    file_system,
    grep_files,
    list_files,
    read_file,
    write_file,
)
from app.domain.tools.human_input import request_approval

# Phase 22: Environment Interaction Tools
from app.domain.tools.environment.desktop import desktop_control
from app.domain.tools.environment.mobile import mobile_control
from app.domain.tools.environment.find_element import find_element
from app.domain.tools.vision import analyze_image
from app.domain.tools.execution import execute_learned_skill
from app.domain.tools.utils.time_tools import wait

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
                    # (Some specialized tools might satisfy deps later)
                    logger.debug(f"Skipping module {name} during scan: {e}")
        else:
            # It's a single module
            self._register_tools_from_module(package)

    def _register_tools_from_module(self, module):
        """
        Inspect a module for @evoloop_tool decorated functions (which become BaseTool instances).
        """
        for name, obj in inspect.getmembers(module):
            # We look for BaseTool instances that have our special marker
            if isinstance(obj, BaseTool):
                # LangChain StructuredTool wraps the function in .func (sync) or .coroutine (async)
                # We need to check the wrapped function for our marker
                try:
                    wrapped_func = getattr(obj, "func", None) or getattr(obj, "coroutine", None)

                    if wrapped_func and getattr(wrapped_func, "is_evoloop_active", False):
                        # Check for duplicates? For now, we trust the set logic or just append
                        # We might want to avoid re-registering the same tool object
                        if obj not in self._tools:
                            self._tools.append(obj)
                            logger.debug(f"Registered tool: {obj.name} from {module.__name__}")
                except Exception as e:
                    # Some objects might raise errors on getattr inspection
                    logger.warning(f"Failed to inspect tool {name} in {module.__name__}: {e}")

    def get_all_tools(self) -> list[BaseTool]:
        """
        Return all registered tools.
        """
        return list(self._tools)


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


def _build_static_tool_map() -> dict[str, BaseTool]:
    """
    Build a name -> BaseTool mapping from all statically imported tools.
    This replaces the manually maintained dict in get_tools_by_names.
    """
    tool_map: dict[str, BaseTool] = {}

    # All statically imported tools (from module-level imports above)
    static_tools = [
        read_file, write_file, edit_file, list_files, grep_files, file_system,
        consult_lsp, explore_codebase, manage_git,
        create_plan, update_step_status, analyze_feasibility,
        manage_memory, consult_architecture,
        search_web, request_approval, execute_learned_skill,
        wait, desktop_control, mobile_control, find_element, analyze_image,
        write_document, edit_document,
    ]

    # Optional tools
    try:
        static_tools.append(learn_skill_from_trace)
    except Exception:
        pass

    try:
        from app.domain.research.tools import crawl_url
        static_tools.append(crawl_url)
    except ImportError:
        pass

    for tool in static_tools:
        if isinstance(tool, BaseTool) and tool.name:
            tool_map[tool.name] = tool

    return tool_map


def _report_missing_tools(node_role: str, missing_tools: list[str]):
    """
    Report missing tools via logger.error and EvoCloud activity monitor.
    Strict mode: no silent fallback — missing tools are explicitly surfaced.
    """
    logger.error(
        f"[ToolRBAC] Missing tools for role '{node_role}': {missing_tools}. "
        f"These tools are declared in YAML but not found in Registry or MCP. "
        f"Agent will operate with reduced capability."
    )

    # Report to EvoCloud via Activity Monitor
    try:
        from app.core.monitoring.activity import activity_monitor
        import json
        from datetime import datetime, timezone

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
    """
    Get tools for a specific agent node/role from YAML config (strict mode).

    Loads tool names from agent_main.yaml (node.tools or role_tools section),
    hydrates them to BaseTool objects, and reports any missing tools.

    Args:
        node_role: The role identifier (e.g. "supervisor", "developer", "coder")
        config_path: Optional path to YAML config. Defaults to agent_main.yaml.

    Returns:
        List of available BaseTool objects for this role.
    """
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

    # 3. If still no tools declared, this is a config gap — report it
    if not tool_names:
        logger.warning(
            f"[ToolRBAC] No tools declared for role '{node_role}' in YAML config. "
            f"Agent will have no tools available."
        )
        _report_missing_tools(node_role, [f"<no config for role '{node_role}'>"])
        return []

    # 4. Hydrate tool names to BaseTool objects
    return get_tools_by_names(tool_names, source_role=node_role)


def get_tools_by_names(
    tool_names: list[str],
    source_role: str | None = None,
) -> list[BaseTool]:
    """
    Hydrate a list of tool names into actual BaseTool objects.
    Uses static import map + AutoDiscoveryRegistry + MCP as lookup sources.

    Args:
        tool_names: List of tool name strings to look up.
        source_role: Optional role name (for missing-tool reporting).

    Returns:
        List of found BaseTool objects.
    """
    # Build lookup map from static imports
    tool_map = _build_static_tool_map()

    # Extend with AutoDiscoveryRegistry tools
    try:
        from app.core.tools.registry import REGISTRY
        for tool in REGISTRY.get_all_tools():
            if tool.name and tool.name not in tool_map:
                tool_map[tool.name] = tool
    except Exception:
        pass

    # Extend with MCP tools
    try:
        from app.infrastructure.mcp.client import mcp_client_manager
        for tool in mcp_client_manager.get_tools():
            if tool.name and tool.name not in tool_map:
                tool_map[tool.name] = tool
    except Exception:
        pass

    # Hydrate
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
