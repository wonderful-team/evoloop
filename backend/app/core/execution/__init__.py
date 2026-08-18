# Core Execution Module
# Provides Sandbox and Terminal infrastructure for command execution.
#
# Lazy exports: ``import app.core.execution.macro.event`` (or any submodule)
# must not pull the whole sandbox/terminal stack into infra load, so the heavy
# modules are loaded on first symbol access instead of at package import.

from __future__ import annotations

import importlib

__all__ = [
    "Sandbox",
    "SandboxFactory",
    "LocalSandbox",
    "TerminalManager",
    "terminal_manager",
]

_SYMBOL_MODULES: dict[str, str] = {
    "Sandbox": "app.core.execution.sandbox.base",
    "SandboxFactory": "app.core.execution.sandbox.factory",
    "LocalSandbox": "app.core.execution.sandbox.local",
    "TerminalManager": "app.core.execution.terminal.manager",
    "terminal_manager": "app.core.execution.terminal.manager",
}


def __getattr__(name: str):
    module_path = _SYMBOL_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
