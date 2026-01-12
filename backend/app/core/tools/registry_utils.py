import importlib
import inspect
import logging
import pkgutil

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

class AutoDiscoveryRegistry:
    """
    Registry that automatically scans packages for tools marked with @evoloop_tool.
    """
    def __init__(self):
        self._tools: list[BaseTool] = []
        self._scanned_packages = set()

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
    from app.domain.planning.tools import (
        analyze_feasibility,
        create_plan,
        update_step_status,
    )
    from app.domain.tools.coding.lsp import consult_lsp
    from app.domain.tools.facades import (
        consult_architecture,
        explore_codebase,
        grep_files,
        manage_file,
        manage_file_docs_only,
        manage_file_read_only,
        manage_git,
        manage_memory,
    )
    try:
        from app.domain.research.tools import search_web
    except ImportError:
         search_web = None

    # Core Tools everyone gets (Read-Only)
    common_read = [explore_codebase, grep_files]

    if node_role == "supervisor":
        # Supervisor: Read + Plan + Docs + Memory + Git (Read)
        tools = [
            manage_file_read_only, manage_file_docs_only,
            manage_memory,
            create_plan, update_step_status, analyze_feasibility, # Plan Tools
            consult_architecture,
            *common_read
        ]

        # Phase 11: Learning Tool (Dynamic Import)
        try:
            from app.domain.learning.tools import learn_skill_from_trace
            tools.append(learn_skill_from_trace)
        except ImportError:
            pass

        return tools

    elif node_role == "coder":
        # Coder: Full Write + LSP + Git + Memory
        return [
            manage_file, # Full Power
            consult_lsp,
            manage_git,
            manage_memory,
            consult_architecture,
            *common_read
        ]

    elif node_role == "planner":
        # Planner: Read Only + Planning Tools
        return [
            manage_file_read_only,
            create_plan, update_step_status, analyze_feasibility,
            consult_architecture,
            *common_read
        ]

    elif node_role == "researcher":
        # Researcher: Read Only + Web Search + Crawler + Memory
        from app.domain.research.tools import crawl_url
        tools = [
            manage_file_read_only,
            manage_memory,
            crawl_url,
            *common_read
        ]
        if search_web: tools.append(search_web)
        return tools

    elif node_role == "requirement_analyst":
        # Requirement Analyst: Read + Docs
        return [
            manage_file_read_only, manage_file_docs_only,
            manage_memory,
            *common_read
        ]

    elif node_role == "tester":
        # Tester: Read + Write Tests (Full for now, could be restricted to tests/) + Run Command
        # Need to import run_command if it exists
        return [
            manage_file, # Needs to write tests
            manage_memory,
            *common_read
        ]

    # Fallback to safe defaults
    return [manage_file_read_only]
