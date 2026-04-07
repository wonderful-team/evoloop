"""
Event Handler Decorators
========================

Provides decorators for automatic event handler registration.

Usage:
    from app.core.events.decorators import event_subscribe, event_register
    from app.core.rewind.events import RewindEventType
    
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
    Decorator to mark a method as an event handler.
    
    The method will be automatically registered to handle the specified event type.
    
    Args:
        event_type: The event type to subscribe to (string or Enum)
        
    Returns:
        The decorated function (unchanged)
        
    Example:
        class MyHandler:
            @event_subscribe(MyEventType.SOME_EVENT)
            async def on_some_event(self, event):
                print(f"Received: {event}")
    """
    def decorator(func: F) -> F:
        # Store event types on the function for later registration
        if not hasattr(func, "_event_types"):
            func._event_types = []
        func._event_types.append(event_type)
        
        # Mark function as an event handler
        func._is_event_handler = True
        
        return func
    
    return decorator


def register_instance_handlers(instance: Any, bus: Any = None) -> None:
    """
    Register all decorated handlers on an instance to the event bus.
    
    This should be called after creating an instance of a handler class.
    
    Args:
        instance: The handler instance to register
        bus: The event bus to subscribe to (defaults to system_bus)
    """
    if bus is None:
        bus = system_bus
    
    instance_class = instance.__class__
    registered_count = 0
    
    # Get all methods that have event handlers
    for method_name in dir(instance_class):
        method = getattr(instance_class, method_name, None)
        if not callable(method) or not hasattr(method, "_is_event_handler"):
            continue
        
        # Get event types for this method
        event_types = getattr(method, "_event_types", [])
        
        # Create bound method for this instance
        bound_method = getattr(instance, method_name)
        
        # Subscribe to each event type
        for event_type in event_types:
            bus.subscribe(event_type, bound_method)
            registered_count += 1
            logger.debug(f"[EventRegister] {instance_class.__name__}.{method_name} -> {event_type}")
    
    if registered_count > 0:
        logger.info(f"[EventRegister] {instance_class.__name__}: {registered_count} handlers registered")


def event_register(bus: Any = None) -> Callable[[type], type]:
    """
    Class decorator to automatically register all @event_subscribe decorated methods.
    
    When the class is instantiated, all methods decorated with @event_subscribe
    will be automatically registered to the event bus.
    
    Args:
        bus: The event bus to subscribe to (defaults to system_bus)
        
    Returns:
        The decorated class
        
    Example:
        @event_register()
        class FileRewind:
            @event_subscribe(RewindEventType.FILES_CLEANUP)
            async def _handle_files_cleanup(self, event): ...
    """
    if bus is None:
        bus = system_bus
    
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
        from app.core.environment.events import event_bus
        
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
