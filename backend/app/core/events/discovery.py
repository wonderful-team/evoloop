"""
Event Handler Discovery
=======================

Automatically discovers and registers event handlers at application startup.

This module provides automatic discovery of event handlers decorated with
@event_register or @event_register_with_bus, eliminating the need for manual
registration or maintaining hardcoded lists.

Usage:
    from app.core.events.discovery import auto_discover_handlers
    
    # Auto-discover all handlers in app/ directory
    auto_discover_handlers()

The discovery process:
1. Recursively scans all Python modules under specified root directories
2. Imports each module to trigger class definitions
3. Finds all classes with @event_register decorator
4. Instantiates each class (which triggers event registration)

Features:
- Recursive module scanning
- Automatic decorator detection
- Duplicate registration prevention
- Configurable scan roots
"""

import importlib
import inspect
import logging
import pkgutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)

# Track which modules have been scanned to prevent duplicates
_scanned_modules: set[str] = set()
_registered_handlers: set[type] = set()

# Default root packages to scan for event handlers
DEFAULT_SCAN_ROOTS = [
    "app.core",
    "app.domain",
    "app.infrastructure",
]


def _has_auto_register_decorator(cls: type) -> bool:
    """
    Check if a class has @event_register or @event_register_with_bus decorator.
    
    Args:
        cls: The class to check
        
    Returns:
        True if the class has the auto_register marker
    """
    # Check for decorator marker on class
    if hasattr(cls, '_auto_register') and cls._auto_register:
        return True
    
    # Check for decorator marker on __init__
    if hasattr(cls, '__init__') and hasattr(cls.__init__, '_auto_register'):
        return True
    
    return False


def _find_handler_classes(module: ModuleType) -> list[type]:
    """
    Find all handler classes in a module that have @event_register decorator.
    
    Args:
        module: The module to inspect
        
    Returns:
        List of handler classes with @event_register decorator
    """
    classes = []
    
    for name, obj in inspect.getmembers(module, inspect.isclass):
        # Skip imported classes (only check classes defined in this module)
        if obj.__module__ != module.__name__:
            continue
        
        # Check if class has @event_register decorator
        if _has_auto_register_decorator(obj):
            classes.append(obj)
            logger.debug(f"[Discovery] Found handler class: {obj.__module__}.{obj.__name__}")
    
    return classes


def _scan_module_recursive(
    module_name: str,
    scanned: set[str] | None = None
) -> list[type]:
    """
    Recursively scan a module and its submodules for event handlers.
    
    Args:
        module_name: The root module name to scan (e.g., "app.core")
        scanned: Set of already scanned module names (to prevent cycles)
        
    Returns:
        List of discovered handler classes
    """
    if scanned is None:
        scanned = set()
    
    # Prevent duplicate scanning
    if module_name in scanned:
        return []
    
    # Prevent re-scanning already processed modules
    if module_name in _scanned_modules:
        return []
    
    scanned.add(module_name)
    _scanned_modules.add(module_name)
    
    discovered_classes = []
    
    try:
        # Import the module
        module = importlib.import_module(module_name)
        
        # Find handler classes in this module
        classes = _find_handler_classes(module)
        discovered_classes.extend(classes)
        
        # Recursively scan submodules
        if hasattr(module, '__path__'):
            for finder, name, ispkg in pkgutil.iter_modules(module.__path__):
                submodule_name = f"{module_name}.{name}"
                
                # Skip already scanned modules
                if submodule_name in scanned or submodule_name in _scanned_modules:
                    continue
                
                try:
                    # Recursively scan submodule
                    sub_classes = _scan_module_recursive(submodule_name, scanned)
                    discovered_classes.extend(sub_classes)
                except Exception as e:
                    logger.debug(f"[Discovery] Failed to scan {submodule_name}: {e}")
                    
    except ImportError as e:
        logger.debug(f"[Discovery] Failed to import {module_name}: {e}")
    except Exception as e:
        logger.warning(f"[Discovery] Error scanning {module_name}: {e}")
    
    return discovered_classes


def auto_discover_handlers(
    scan_roots: list[str] | None = None,
    instantiate: bool = True
) -> list[type]:
    """
    Auto-discover and register event handlers from specified root packages.
    
    This function recursively scans the specified Python packages, finds all
    classes decorated with @event_register or @event_register_with_bus, and
    instantiates them to trigger automatic event handler registration.
    
    Args:
        scan_roots: List of root package names to scan (e.g., ["app.core", "app.domain"])
                   If None, uses DEFAULT_SCAN_ROOTS
        instantiate: If True, instantiate each discovered class
        
    Returns:
        List of discovered handler classes
        
    Example:
        # Discover all handlers in default locations
        handlers = auto_discover_handlers()
        
        # Or scan specific packages
        handlers = auto_discover_handlers(["app.core", "app.domain"])
    """
    if scan_roots is None:
        scan_roots = DEFAULT_SCAN_ROOTS
    
    discovered_classes = []
    instantiated_handlers = []
    
    logger.info(f"[Discovery] Starting recursive scan of {len(scan_roots)} root packages...")
    
    for root_package in scan_roots:
        try:
            classes = _scan_module_recursive(root_package)
            discovered_classes.extend(classes)
        except Exception as e:
            logger.warning(f"[Discovery] Error scanning {root_package}: {e}")
    
    # Instantiate each discovered class (triggers auto-registration)
    if instantiate:
        for cls in discovered_classes:
            # Prevent duplicate instantiation
            if cls in _registered_handlers:
                continue
            
            try:
                instance = cls()
                instantiated_handlers.append(instance)
                _registered_handlers.add(cls)
                logger.debug(f"[Discovery] Instantiated {cls.__module__}.{cls.__name__}")
            except Exception as e:
                logger.warning(f"[Discovery] Failed to instantiate {cls.__name__}: {e}")
    
    logger.info(f"[Discovery] ✓ Discovered {len(discovered_classes)} handler classes, "
                f"instantiated {len(instantiated_handlers)}")
    
    return discovered_classes


def auto_discover_all() -> None:
    """
    Convenience function to auto-discover all event handlers in the application.
    
    This is the main entry point for application startup.
    Scans all default root packages recursively.
    """
    auto_discover_handlers(DEFAULT_SCAN_ROOTS)
    logger.info("[Discovery] ✓ All event handlers auto-discovered and registered")


def reset_discovery_cache() -> None:
    """
    Reset the discovery cache. Useful for testing.
    """
    global _scanned_modules, _registered_handlers
    _scanned_modules.clear()
    _registered_handlers.clear()
    logger.debug("[Discovery] Cache reset")


def get_discovered_stats() -> dict[str, int]:
    """
    Get discovery statistics.
    
    Returns:
        Dict with 'scanned_modules' and 'registered_handlers' counts
    """
    return {
        'scanned_modules': len(_scanned_modules),
        'registered_handlers': len(_registered_handlers),
    }
