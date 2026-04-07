# All Event Handlers Now Use Annotations ✅

## Summary
All event handlers in `app/core/` now use the unified annotation-based registration system.

## Decorators

### `@handles(event_type)`
Marks a method as an event handler for the specified event type.

### `@auto_register()`
Class decorator for system_bus. Auto-registers handlers on instantiation.

### `@auto_register_with_bus(bus)`
Class decorator for custom event bus (e.g., AwakenEventBus).

## Updated Files

### Rewind Handlers (app/core/)
| File | Decorators |
|------|-----------|
| `app/core/file/rewind.py` | `@auto_register()`, `@handles(...)` |
| `app/core/memory/rewind.py` | `@auto_register()`, `@handles(...)` |
| `app/core/engine/rewind/state.py` | `@auto_register()`, `@handles(...)` |

### Other Core Handlers
| File | Decorators |
|------|-----------|
| `app/core/learning/orchestrator.py` | `@auto_register()`, `@handles(...)` |
| `app/core/learning/self_healing.py` | `@auto_register()`, `@handles(...)` |
| `app/core/environment/handlers.py` | `@auto_register_with_bus(event_bus)`, `@handles(...)` |
| `app/core/events/bridge.py` | `@auto_register()` |

### Domain Handlers
| File | Decorators |
|------|-----------|
| `app/domain/codebase/indexing/event_handlers.py` | `@auto_register()`, `@handles(...)` |
| `app/domain/codebase/events.py` | `@auto_register()`, `@handles(...)` |

## New Decorator Support

### For Custom EventBus
```python
from app.core.environment.events import event_bus
from app.core.events.decorators import auto_register_with_bus, handles

@auto_register_with_bus(event_bus)
class DeviceEventHandler:
    @handles(EventType.DEVICE_CONNECTED)
    async def on_device_connected(self, event): ...
```

## Main.py Simplified

```python
# Single line discovers and registers ALL handlers
auto_discover_handlers()

# Only special cases need manual registration:
register_event_bridge()  # Uses subscribe_all for all events
```

## Files Changed

### New/Updated Decorator Files
- `app/core/events/decorators.py` - Added `@auto_register_with_bus()`
- `app/core/events/discovery.py` - Discovery mechanism

### Converted to Annotations
1. `app/core/file/rewind.py`
2. `app/core/memory/rewind.py`
3. `app/core/engine/rewind/state.py`
4. `app/core/learning/orchestrator.py`
5. `app/core/learning/self_healing.py`
6. `app/core/environment/handlers.py`
7. `app/domain/codebase/indexing/event_handlers.py`
8. `app/domain/codebase/events.py`
9. `app/core/events/bridge.py`

## Test Results
- ✅ 27/27 tests passing
- ✅ All handlers using unified annotation system
- ✅ Backward compatibility maintained

## Backward Compatibility

All `register_*()` functions are kept but now simply instantiate the handler classes:

```python
def register_learning_handlers():
    """Kept for compatibility - triggers auto-registration."""
    LearningOrchestrator()  # Auto-registered via decorator
    MacroSelfHealingAdvisor()  # Auto-registered via decorator
```
