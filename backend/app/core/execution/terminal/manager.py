import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Dict

from app.i18n.service import i18n
from app.core.context.manager import ContextManager

logger = logging.getLogger(__name__)


@dataclass
class TerminalSession:
    """
    Represents a persistent shell session for a specific context (Thread/Task).
    """
    cwd: str
    env: Dict[str, str] = field(default_factory=lambda: os.environ.copy())
    
    def __post_init__(self):
        # Ensure minimal env
        if "TERM" not in self.env:
            self.env["TERM"] = "xterm-256color"


class TerminalManager:
    """
    Manages terminal sessions based on the current execution context.
    No longer a singleton with shared state. State is stored in Context or Memory.
    For V1 refactor, we will maintain an in-memory map keyed by thread_id/context_id 
    until we move to a proper Kernel/Sandbox architecture.
    """
    
    # In-memory storage for active sessions
    # Key: thread_id or session_id
    _sessions: Dict[str, TerminalSession] = {}

    @classmethod
    def _get_session_key(cls) -> str:
        ctx = ContextManager.current()
        # Prefer thread_id, fallback to request_id
        return ctx.thread_id or ctx.request_id or "global"

    @classmethod
    def get_session(cls) -> TerminalSession:
        key = cls._get_session_key()
        if key not in cls._sessions:
             # Initialize with context working directory if available
            ctx = ContextManager.current()
            initial_cwd = ctx.working_directory or os.getcwd()
            
            # Create new session
            cls._sessions[key] = TerminalSession(cwd=initial_cwd)
            logger.debug(f"Created new TerminalSession for {key} at {initial_cwd}")
            
        return cls._sessions[key]

    @classmethod
    def run_command(cls, command: str, timeout: int = 60) -> tuple[str, str, int]:
        """
        Runs a command in the current context's persistent session.
        """
        session = cls.get_session()
        command = command.strip()

        # 1. Handle 'cd' manually
        if command.startswith("cd "):
            path = command[3:].strip()
            return cls._change_directory(session, path)

        # 2. Handle 'export' manually (simple case)
        if command.startswith("export "):
            return cls._handle_export(session, command)

        # 3. Run actual subprocess
        try:
            # logger.debug(f"Running command: '{command}' in {session.cwd}")
            process = subprocess.run(
                command,
                cwd=session.cwd,
                env=session.env,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            stdout = process.stdout
            stderr = process.stderr
            returncode = process.returncode

            return stdout, stderr, returncode

        except subprocess.TimeoutExpired:
            return "", i18n.get("prompts.domain_tools.terminal.timeout"), 124
        except Exception as e:
            return "", str(e), 1

    @classmethod
    def _change_directory(cls, session: TerminalSession, path: str) -> tuple[str, str, int]:
        # Resolve absolute path relative to current tracked CWD
        # Handle ~ expansion
        if path.startswith("~"):
            path = os.path.expanduser(path)
            
        new_path = os.path.abspath(os.path.join(session.cwd, path))

        if os.path.isdir(new_path):
            session.cwd = new_path
            return f"Changed directory to {new_path}", "", 0 # i18n? keeping simple for now to avoid circulars
        else:
            return "", f"cd: no such file or directory: {path}", 1

    @classmethod
    def _handle_export(cls, session: TerminalSession, command: str) -> tuple[str, str, int]:
        # export KEY=VALUE
        # Remove 'export '
        kv = command[7:].strip()
        if "=" in kv:
            key, value = kv.split("=", 1)
            # Remove quotes
            value = value.strip("'").strip('"')
            session.env[key] = value
            return f"Exported {key}", "", 0

        return "", "export: invalid format", 1


# Global Accessor (Stateless Class)
terminal_manager = TerminalManager
