# Core Execution Module
# Provides Sandbox and Terminal infrastructure for command execution.

from app.core.execution.sandbox.base import Sandbox
from app.core.execution.sandbox.factory import SandboxFactory
from app.core.execution.sandbox.local import LocalSandbox
from app.core.execution.terminal.manager import TerminalManager, terminal_manager

__all__ = [
    "Sandbox",
    "SandboxFactory",
    "LocalSandbox",
    "TerminalManager",
    "terminal_manager",
]
