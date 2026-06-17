"""
Event Handler Decorators
========================

Provides decorators for automatic event handler registration.

Usage:
    from app.core.events.decorators import event_subscribe, event_register
    from app.core.engine.rewind.event import RewindEventType
    
    @event_register()
    class FileRewind:
        @event_subscribe(RewindEventType.FILES_CLEANUP)
        async def _handle_files_cleanup(self, event):
            ...
        
        @event_subscribe(RewindEventType.REWIND_REQUESTED)
        async def _handle_rewind_requested(self, event):
            ...

The handlers are automatically registered when the module is imported.
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from app.core.events import system_bus

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def event_subscribe(event_type: str | Any) -> Callable[[F], F]:
    """
    Decorator to mark a method as an event handler for a specific type.
    """
    def decorator(func: F) -> F:
        if not hasattr(func, "_event_types"):
            func._event_types = []
        func._event_types.append(event_type)
        func._is_event_handler = True
        return func

    return decorator


def event_subscribe_all() -> Callable[[F], F]:
    """
    Decorator to mark a method as a global event handler (subscriber to all events).
    """
    def decorator(func: F) -> F:
        func._is_event_handler_all = True
        return func

    return decorator


def register_instance_handlers(instance: Any, bus: Any = None) -> None:
    """
    Register all decorated handlers on an instance to the event bus.
    """
    if bus is None:
        bus = system_bus

    instance_class = instance.__class__
    registered_count = 0

    # Get all methods that have event handlers
    for method_name in dir(instance_class):
        method = getattr(instance, method_name, None)
        if not callable(method):
            continue

        # 1. Specific Type Subscriptions
        if hasattr(method, "_is_event_handler"):
            event_types = getattr(method, "_event_types", [])
            for event_type in event_types:
                bus.subscribe(event_type, method)
                registered_count += 1

        # 2. Global Subscriptions (Subscribe All)
        if hasattr(method, "_is_event_handler_all"):
            bus.subscribe_all(method)
            registered_count += 1

    if registered_count > 0:
        logger.info(f"[EventRegister] {instance_class.__name__}: {registered_count} handlers registered")


def event_register(arg: Any = None) -> Any:
    """
    Class decorator to automatically register all decorated methods.
    Supports both @event_register() and @event_register.
    """
    if isinstance(arg, type):
        # Called as @event_register
        return event_register_with_bus(system_bus)(arg)
    
    # Called as @event_register(bus=...) or @event_register()
    bus = arg or system_bus
    return event_register_with_bus(bus)


def event_register_with_bus(bus: Any) -> Callable[[type], type]:
    """
    Class decorator to automatically register all @event_subscribe decorated methods
    to a specific event bus.
    
    This is useful when you have multiple event buses in the system
    (e.g., system_bus for global events, event_bus for domain-specific events).
    
    Args:
        bus: The specific event bus to subscribe to
        
    Returns:
        The decorated class
        
    Example:
        from app.core.environment.bus import event_bus
        
        @event_register_with_bus(event_bus)
        class DeviceEventHandler:
            @event_subscribe(EventType.DEVICE_CONNECTED)
            async def on_device_connected(self, event): ...
    """
    def decorator(cls: type) -> type:
        # Mark the class for discovery
        cls._auto_register = True
        cls._event_bus = bus  # Store the bus for reference

        original_init = cls.__init__

        def new_init(self, *args, **kwargs):
            # Call original __init__
            original_init(self, *args, **kwargs)
            # Register handlers after init
            register_instance_handlers(self, bus)

        # Mark the new __init__ for discovery compatibility
        new_init._auto_register = True
        cls.__init__ = new_init
        return cls

    return decorator
