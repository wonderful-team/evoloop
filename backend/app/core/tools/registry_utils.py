import importlib
import inspect
import logging
import pkgutil

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
    list_files,
    read_file,
    write_file,
)
from app.domain.tools.human_input import request_approval
from app.infrastructure.filesystem.tool import grep_files

logger = logging.getLogger(__name__)


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
            for _, name, ispkg in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
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


def get_node_tools(node_role: str) -> list[BaseTool]:
    """
    Get tools customized for a specific agent node (RBAC).
    """
    # Import locally to avoid circular dependencies with registry
    # from app.domain.planning.tools import create_plan, update_step_status, analyze_feasibility
    # Note: Planning tools are model-bound manually in planner usually, but we include them here if they are standardized tools.
    # For now, we import them if they exist as tool wrappers.
    # Assuming they are available via facades or planning module.
    # Checking planner.py, they are imported from app.domain.planning.tools.
    # Core Tools everyone gets (Read-Only)
    common_read = [explore_codebase, grep_files]

    if node_role == "supervisor":
        # Supervisor: Read + Plan + Docs + Memory + Git (Read) + HITL
        tools = [
            read_file,
            list_files,
            manage_memory,
            create_plan,
            update_step_status,
            analyze_feasibility,  # Plan Tools
            consult_architecture,
            request_approval,  # Supervisor needs HITL for plan confirmation
            *common_read,
        ]

        # Phase 11: Learning Tool (Dynamic Import)
        try:
            tools.append(learn_skill_from_trace)
        except ImportError:
            pass

        return tools

    elif node_role == "coder":
        # Coder: Full Write + LSP + Git + Memory + HITL (Phase 18: Atomic Tools)
        return [
            read_file,
            write_file,
            edit_file,
            list_files,
            file_system,
            consult_lsp,
            manage_git,
            manage_memory,
            consult_architecture,
            request_approval,  # HITL for high-risk operations
            *common_read,
        ]

    elif node_role == "planner":
        # Planner: Read Only + Planning Tools + HITL
        return [
            read_file,
            list_files,
            create_plan,
            update_step_status,
            analyze_feasibility,
            consult_architecture,
            request_approval,  # HITL for complex plans
            *common_read,
        ]

    elif node_role == "researcher":
        # Researcher: Read Only + Web Search + Crawler + Memory
        from app.domain.research.tools import crawl_url

        tools = [read_file, list_files, manage_memory, crawl_url, *common_read]
        if search_web:
            tools.append(search_web)
        return tools

    elif node_role == "requirement_analyst":
        # Requirement Analyst: Read + Docs
        return [
            read_file,
            list_files,
            write_document,
            edit_document,
            manage_memory,
            *common_read,
        ]

    elif node_role == "tester":
        # Tester: Read + Write Tests (Phase 18: Atomic Tools)
        return [
            read_file,
            write_file,
            edit_file,
            list_files,
            manage_memory,
            *common_read,
        ]

    # Fallback to safe defaults (read-only)
    return [read_file, list_files]
