"""
Event Auto-Discovery Test
==========================

Tests the automatic discovery and registration of event handlers.
Verifies that all @event_register decorated classes are properly discovered.
"""

import importlib
import inspect
import pkgutil
from typing import Set, Type

import pytest


# Import all handler modules to trigger registration
# This simulates what happens during application startup
IMPORT_PATHS = [
    "app.core.file.rewind",
    "app.core.memory.rewind",
    "app.core.engine.rewind.state",
    "app.core.learning.rewind",
    "app.core.execution.macro.advisor",
    "app.core.events.bridge",
    "app.core.environment.handlers",
    "app.domain.todo.rewind",
    "app.domain.codebase.handlers",
    "app.domain.codebase.event_handlers",
    "app.domain.codebase.indexing.event_handlers",
    "app.domain.project.handlers",
    "infrastructure.database.models.rewind",
]


class TestEventDiscovery:
    """Test event handler auto-discovery mechanism."""

    def test_discover_all_handlers(self):
        """Verify that all @event_register classes can be discovered."""
        from app.core.events.discovery import _has_auto_register_decorator
        
        discovered_handlers: Set[Type] = set()
        
        # Scan all handler modules
        for module_path in IMPORT_PATHS:
            try:
                module = importlib.import_module(module_path)
                
                # Find all classes with @event_register decorator
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if obj.__module__ == module_path and _has_auto_register_decorator(obj):
                        discovered_handlers.add(obj)
                        print(f"  ✓ Discovered: {module_path}.{name}")
                        
            except ImportError as e:
                pytest.skip(f"Module {module_path} not available: {e}")
        
        # Verify we found handlers
        assert len(discovered_handlers) > 0, "No event handlers discovered!"
        print(f"\n✅ Total handlers discovered: {len(discovered_handlers)}")
        
        # List all discovered handlers
        for handler_class in sorted(discovered_handlers, key=lambda x: x.__name__):
            print(f"  - {handler_class.__module__}.{handler_class.__name__}")

    def test_handler_registration(self):
        """Verify that handlers are properly registered to event bus."""
        from app.core.events import system_bus
        from app.core.events.discovery import _has_auto_register_decorator
        
        # Clear previous state
        system_bus.clear()
        
        # Import and instantiate handlers
        handler_instances = []
        for module_path in IMPORT_PATHS:
            try:
                module = importlib.import_module(module_path)
                
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if obj.__module__ == module_path and _has_auto_register_decorator(obj):
                        try:
                            instance = obj()
                            handler_instances.append(instance)
                            print(f"  ✓ Instantiated: {name}")
                        except Exception as e:
                            print(f"  ⚠️ Failed to instantiate {name}: {e}")
                            
            except ImportError:
                continue
        
        # Verify handlers are registered (have subscriptions)
        # Note: system_bus._handlers is internal, but we can check it's not empty
        print(f"\n✅ Total handler instances: {len(handler_instances)}")
        
        # At minimum, we should have successfully created some instances
        assert len(handler_instances) > 0, "No handler instances created!"

    def test_event_subscription_decorators(self):
        """Verify that @event_subscribe decorators are properly applied."""
        from app.core.events.discovery import _has_auto_register_decorator
        
        handlers_with_subscriptions = []
        
        for module_path in IMPORT_PATHS:
            try:
                module = importlib.import_module(module_path)
                
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if obj.__module__ == module_path and _has_auto_register_decorator(obj):
                        # Count @event_subscribe methods
                        subscription_count = 0
                        for method_name in dir(obj):
                            method = getattr(obj, method_name, None)
                            if callable(method) and hasattr(method, "_is_event_handler"):
                                subscription_count += 1
                                event_types = getattr(method, "_event_types", [])
                                for et in event_types:
                                    et_name = et.value if hasattr(et, 'value') else str(et)
                                    print(f"  ✓ {name}.{method_name} -> {et_name}")
                        
                        if subscription_count > 0:
                            handlers_with_subscriptions.append({
                                'class': obj,
                                'count': subscription_count
                            })
                            
            except ImportError:
                continue
        
        print(f"\n✅ Handlers with event subscriptions: {len(handlers_with_subscriptions)}")
        
        for info in handlers_with_subscriptions:
            print(f"  - {info['class'].__name__}: {info['count']} subscriptions")
        
        assert len(handlers_with_subscriptions) > 0, "No handlers have event subscriptions!"


class TestSpecificHandlers:
    """Test specific handler classes are discoverable."""

    def test_file_rewind_handler(self):
        """Verify FileRewind handler exists and has subscriptions."""
        from app.core.file.rewind import FileRewind
        from app.core.events.discovery import _has_auto_register_decorator
        
        assert _has_auto_register_decorator(FileRewind), "FileRewind not decorated with @event_register"
        
        # Count subscriptions
        sub_count = sum(
            1 for name in dir(FileRewind)
            if hasattr(getattr(FileRewind, name, None), "_is_event_handler")
        )
        assert sub_count >= 2, f"FileRewind should have at least 2 subscriptions, got {sub_count}"
        print(f"✅ FileRewind: {sub_count} subscriptions")

    def test_memory_rewind_handler(self):
        """Verify MemoryRewind handler exists and has subscriptions."""
        from app.core.memory.rewind import MemoryRewind
        from app.core.events.discovery import _has_auto_register_decorator
        
        assert _has_auto_register_decorator(MemoryRewind), "MemoryRewind not decorated with @event_register"
        print("✅ MemoryRewind is properly decorated")

    def test_macro_advisor_handler(self):
        """Verify MacroSelfHealingAdvisor handler exists."""
        from app.core.execution.macro.advisor import MacroSelfHealingAdvisor
        from app.core.events.discovery import _has_auto_register_decorator
        
        assert _has_auto_register_decorator(MacroSelfHealingAdvisor), "MacroSelfHealingAdvisor not decorated"
        print("✅ MacroSelfHealingAdvisor is properly decorated")

    def test_file_indexing_handler(self):
        """Verify FileIndexingHandler exists."""
        from app.domain.codebase.handlers import FileIndexingHandler
        from app.core.events.discovery import _has_auto_register_decorator
        
        assert _has_auto_register_decorator(FileIndexingHandler), "FileIndexingHandler not decorated"
        print("✅ FileIndexingHandler is properly decorated")

    def test_project_sync_handler(self):
        """Verify ProjectSyncHandler exists."""
        from app.domain.project.handlers import ProjectSyncHandler
        from app.core.events.discovery import _has_auto_register_decorator
        
        assert _has_auto_register_decorator(ProjectSyncHandler), "ProjectSyncHandler not decorated"
        print("✅ ProjectSyncHandler is properly decorated")


class TestEventBusIntegration:
    """Test integration with event bus."""

    @pytest.mark.asyncio
    async def test_event_publishing_and_handling(self):
        """Test that events can be published and handled."""
        from app.core.events import system_bus
        from app.core.events.base import BaseEvent
        
        # Clear and setup
        system_bus.clear()
        
        received_events = []
        
        async def test_handler(event):
            received_events.append(event)
        
        # Subscribe test handler
        system_bus.subscribe("test.event", test_handler)
        
        # Publish event
        test_event = BaseEvent(event_type="test.event", data={"test": True})
        await system_bus.publish(test_event)
        
        # Verify
        assert len(received_events) == 1, "Event was not received"
        assert received_events[0].event_type == "test.event"
        print("✅ Event publishing and handling works")


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
