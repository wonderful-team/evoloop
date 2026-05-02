"""
AgentEngine - EvoLoop Agent Execution Engine.

Usage:
    from app.core.engine import AgentEngine

    engine = AgentEngine()
    result = await engine.run_node(state, config, system_prompt, tools)

With dependency injection (for testing):
    engine = AgentEngine(llm_factory=mock_llm)
    result = await engine.run_node(...)
"""

# Use lazy imports to avoid triggering heavy module loads on
# submodule imports (e.g., app.core.engine.rewind.events).
# This is critical for test environments where heavy deps are mocked.

__all__ = [
    "AgentEngine",
    "EngineResult",
    "get_default_engine",
    "set_default_engine",
    "ContextTrimmer",
    "EvoMessageConverter",
]

_import_map = {
    "AgentEngine": ("app.core.engine.engine", "AgentEngine"),
    "EngineResult": ("app.core.engine.engine", "EngineResult"),
    "get_default_engine": ("app.core.engine.engine", "get_default_engine"),
    "set_default_engine": ("app.core.engine.engine", "set_default_engine"),
    "ContextTrimmer": ("app.core.engine.context_trimmer", "ContextTrimmer"),
    "EvoMessageConverter": ("app.core.engine.message.converter", "EvoMessageConverter"),
}

def __getattr__(name: str):
    if name in _import_map:
        module_path, obj_name = _import_map[name]
        module = __import__(module_path, fromlist=[obj_name])
        return getattr(module, obj_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
