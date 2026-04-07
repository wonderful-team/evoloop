# Unified Event Registration via Annotations ✅

## Summary
All event handlers in the system now use annotation-based automatic registration.

## Architecture

### Decorators

#### `@handles(event_type)`
Marks a method as an event handler for the specified event type.

```python
from app.core.events.decorators import auto_register, handles

@auto_register()
class FileRewind:
    @handles(RewindEventType.REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event):
        ...
```

#### `@auto_register(bus=None)`
Class decorator that automatically registers all `@handles` decorated methods when the class is instantiated.

### Auto Discovery

```python
from app.core.events.discovery import auto_discover_handlers

# Scan default paths and auto-register all handlers
auto_discover_handlers()

# Or specify custom paths
auto_discover_handlers([
    "app.core.file.rewind",
    "app.core.memory.rewind",
])
```

## Default Scan Paths

All these modules are automatically scanned on startup:

```python
DEFAULT_SCAN_PATHS = [
    # Rewind handlers
    "app.core.file.rewind",
    "app.core.memory.rewind",
    "app.core.engine.rewind.state",
    "app.infrastructure.database.models.rewind",
    "app.domain.todo.rewind",
    "app.domain.learning.rewind",
    # Other event handlers
    "app.core.environment.handlers",
    "app.domain.codebase.indexing.event_handlers",
    "app.core.learning.orchestrator",
    "app.core.learning.self_healing",
    "app.domain.codebase.events",
]
```

## Main.py Changes

### Before (Explicit Registration)
```python
# main.py
from app.core.environment.handlers import register_default_handlers
from app.domain.codebase.indexing.event_handlers import register_indexing_handlers
from app.core.learning.orchestrator import register_learning_handlers

register_default_handlers()
register_indexing_handlers()
register_event_bridge()
register_learning_handlers()

# Rewind handlers
from app.core.file.rewind import FileRewind
from app.core.memory.rewind import MemoryRewind
...
FileRewind()
MemoryRewind()
...
```

### After (Auto Discovery)
```python
# main.py
from app.core.events.discovery import auto_discover_handlers

# Auto-discover all event handlers
auto_discover_handlers()

# Event bridge still needs manual registration
register_event_bridge()
```

## Updated Handlers

| Handler | File | Decorators |
|---------|------|------------|
| FileRewind | `app/core/file/rewind.py` | `@auto_register()`, `@handles(...)` |
| MemoryRewind | `app/core/memory/rewind.py` | `@auto_register()`, `@handles(...)` |
| MessageRewind | `app/infrastructure/database/models/rewind.py` | `@auto_register()`, `@handles(...)` |
| TodoRewind | `app/domain/todo/rewind.py` | `@auto_register()`, `@handles(...)` |
| TraceRewind | `app/domain/learning/rewind.py` | `@auto_register()`, `@handles(...)` |
| StateRewind | `app/core/engine/rewind/state.py` | `@auto_register()`, `@handles(...)` |

## Backward Compatibility

The `register()` class method is preserved for compatibility:

```python
# Still works - backward compatible
FileRewind.register(system_bus)
```

Internally, this calls the same auto-registration mechanism.

## New Files

- `app/core/events/decorators.py` - `@handles` and `@auto_register` decorators
- `app/core/events/discovery.py` - Auto-discovery mechanism

## Benefits

1. **Unified**: All events use the same registration mechanism
2. **Declarative**: Event subscriptions are declared via annotations
3. **Auto-Discovery**: No need to manually import and instantiate handlers
4. **Self-Documenting**: Handler methods clearly show which events they handle
5. **Extensible**: New handlers are automatically discovered

## Test Results
- ✅ 27/27 tests passing
- ✅ All handlers auto-discovered
- ✅ Backward compatibility maintained
