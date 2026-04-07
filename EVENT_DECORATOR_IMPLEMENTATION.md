# Event Handler Decorator Implementation ✅

## Summary
Implemented decorator-based automatic event handler registration for rewind handlers.

## New Decorators

### `@handles(event_type)`
Marks a method as an event handler for the specified event type.

```python
from app.core.events.decorators import auto_register, handles
from app.core.events import RewindEventType

@auto_register()
class FileRewind:
    @handles(RewindEventType.REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event):
        # Automatically registered on instantiation
        ...
    
    @handles(RewindEventType.FILES_CLEANUP)
    async def _handle_files_cleanup(self, event):
        # Automatically registered on instantiation
        ...
```

### `@auto_register(bus=None)`
Class decorator that automatically registers all `@handles` decorated methods when the class is instantiated.

## Files Changed

### New File
- `app/core/events/decorators.py` - Decorator implementations

### Updated Handlers
| Handler | File |
|---------|------|
| FileRewind | `app/core/file/rewind.py` |
| MemoryRewind | `app/core/memory/rewind.py` |
| MessageRewind | `app/infrastructure/database/models/rewind.py` |
| TodoRewind | `app/domain/todo/rewind.py` |
| TraceRewind | `app/domain/learning/rewind.py` |
| StateRewind | `app/core/engine/rewind/state.py` |

### Updated Main
- `app/main.py` - Changed from explicit `.register()` calls to instantiation

## Changes Summary

### Before (Explicit Registration)
```python
# main.py
FileRewind.register(system_bus)
MemoryRewind.register(system_bus)
MessageRewind.register(system_bus)
...
```

### After (Auto-Registration)
```python
# main.py
FileRewind()
MemoryRewind()
MessageRewind()
...
```

## Backward Compatibility

The `register()` class method is preserved for backward compatibility:

```python
# Still works
FileRewind.register(system_bus)
```

Internally, this creates an instance and calls `register_instance_handlers()`.

## Test Results
- ✅ 27/27 tests passing
- ✅ Decorator auto-registration working
- ✅ Manual register() method still working

## Benefits

1. **Declarative**: Event subscriptions are declared via decorators, not code
2. **Less Boilerplate**: No need for explicit registration calls
3. **Self-Documenting**: Handler methods clearly show which events they handle
4. **Type-Safe**: Decorators preserve type information
5. **Flexible**: Supports both auto-registration and manual registration
