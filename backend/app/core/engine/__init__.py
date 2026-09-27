"""EvoLoop engine package — OpenHands SDK kernel (see docs/openhands-sdk-integration.md)."""

# Use lazy imports to avoid triggering heavy module loads on
# submodule imports (e.g., app.core.engine.rewind.events).

__all__ = [
    "EvoMessageConverter",
]

_import_map = {
    "EvoMessageConverter": ("app.core.engine.message.converter", "EvoMessageConverter"),
}


def __getattr__(name: str):
    if name in _import_map:
        module_path, obj_name = _import_map[name]
        module = __import__(module_path, fromlist=[obj_name])
        return getattr(module, obj_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
