import pkgutil
import importlib
import inspect
import logging
from typing import List, Optional
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

class AutoDiscoveryRegistry:
    """
    Registry that automatically scans packages for tools marked with @evoloop_tool.
    """
    def __init__(self):
        self._tools: List[BaseTool] = []
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
                wrapped_func = getattr(obj, "func", None) or getattr(obj, "coroutine", None)
                
                if wrapped_func and getattr(wrapped_func, "is_evoloop_active", False):
                    # Check for duplicates? For now, we trust the set logic or just append
                    # We might want to avoid re-registering the same tool object
                    if obj not in self._tools:
                        self._tools.append(obj)
                        logger.debug(f"Registered tool: {obj.name} from {module.__name__}")

    def get_all_tools(self) -> List[BaseTool]:
        """
        Return all registered tools.
        """
        return list(self._tools)
