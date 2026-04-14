import logging
import os
import pty
import select
import subprocess
import termios
import threading
import time
import uuid
from typing import Tuple, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from app.core.context.manager import ContextManager

logger = logging.getLogger(__name__)


class PersistentTerminal(BaseModel):
    """
    Manages a long-running interactive shell process via PTY with robust signal tracking.
    """
    session_id: str
    cwd: str
    env: dict[str, str]
    
    _master_fd: int = -1
    _proc: Optional[subprocess.Popen] = None

    def model_post_init(self, __context):
        self._start_shell()

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _start_shell(self):
        """Start a persistent bash instance with a PTY."""
        self._master_fd, slave_fd = pty.openpty()
        
        # Disable echo to simplify parsing
        attr = termios.tcgetattr(self._master_fd)
        attr[3] = attr[3] & ~termios.ECHO
        termios.tcsetattr(self._master_fd, termios.TCSANOW, attr)

        shell_env = self.env.copy()
        shell_env["TERM"] = "dumb"
        # We use a blank PS1 since we use unique SIG markers for status
        shell_env["PS1"] = ""

        self._proc = subprocess.Popen(
            ["/bin/bash", "--norc", "--noprofile"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=self.cwd,
            env=shell_env,
            close_fds=True,
            preexec_fn=os.setsid
        )
        os.close(slave_fd)
        
        # Initial stabilization wait
        time.sleep(0.2)
        logger.debug(f"[PTY][{self.session_id}] Shell started (PID: {self._proc.pid}) at {self.cwd}")

    def run_command(self, command: str, timeout: int = 60) -> Tuple[str, int]:
        """Execute a command synchronously and return (output, exit_code)."""
        if self._proc.poll() is not None:
            logger.warning(f"[PTY][{self.session_id}] Shell died. Restarting...")
            self._start_shell()

        # Generate a unique marker for this specific execution
        sig = str(uuid.uuid4())
        marker = f"EVO_SIG_DONE_{sig}_"
        # Wrap command to echo status at the end
        # Use printf for reliable exit code capture: outputs "MARKER0\n" or "MARKER1\n"
        full_cmd = f"{command}\nprintf '{marker}%d\\n' $?\n"
        
        try:
            os.write(self._master_fd, full_cmd.encode())
        except OSError as e:
            logger.error(f"[PTY][{self.session_id}] Master FD write error: {e}")
            self._start_shell()
            os.write(self._master_fd, full_cmd.encode())

        output = b""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            r, _, _ = select.select([self._master_fd], [], [], 0.1)
            if r:
                try:
                    chunk = os.read(self._master_fd, 4096)
                    if not chunk:
                        break
                    output += chunk
                    # Look for the marker sequence
                    if marker.encode() in output:
                        # Check if we have the full signature including exit code and final newline
                        rest = output.split(marker.encode())[1]
                        if b"\n" in rest:
                            break
                except OSError:
                    break
            
            if self._proc.poll() is not None:
                break
        
        text = output.decode("utf-8", errors="replace")
        
        # Parse result by looking for marker followed by exit code
        # Format: "EVO_SIG_DONE_xxx_0" (marker + exit_code as single line)
        marker_with_code = None
        exit_code = -1
        actual_output = text
        
        for line in text.split('\n'):
            if line.startswith(marker):
                marker_with_code = line
                try:
                    exit_code_str = line[len(marker):].strip()
                    exit_code = int(exit_code_str)
                except ValueError:
                    logger.error(f"[PTY][{self.session_id}] Failed to parse exit code from: {line[:100]}")
                    exit_code = -1
                break
        
        if marker_with_code:
            parts = text.split(marker_with_code)
            actual_output = parts[0].strip() if parts else text
        elif time.time() - start_time >= timeout:
            actual_output = text + "\n[Error: Command timed out]"
            exit_code = -1

        # Periodic state sync (CWD)
        self._sync_state()
        
        return actual_output, exit_code

    def _sync_state(self):
        """Silently query the shell for current CWD to keep session state accurate."""
        sig = str(uuid.uuid4())
        marker = f"EVO_PWD_SIG_{sig}_"
        cmd = f"pwd\nprintf '{marker}%d\\n' $?\n"
        os.write(self._master_fd, cmd.encode())
        
        # Short timeout for internal sync
        output = b""
        start_time = time.time()
        while time.time() - start_time < 2:
            r, _, _ = select.select([self._master_fd], [], [], 0.05)
            if r:
                try:
                    chunk = os.read(self._master_fd, 1024)
                    output += chunk
                    if marker.encode() in output: break
                except OSError: break
        
        text = output.decode("utf-8", errors="replace")
        # Look for line starting with marker (format: "EVO_PWD_SIG_xxx_0")
        for line in text.split('\n'):
            if line.startswith(marker):
                new_cwd = text.split(line)[0].strip()
                # Clean up bash non-interactive noise if any
                new_cwd = new_cwd.splitlines()[-1] if "\n" in new_cwd else new_cwd
                if os.path.isdir(new_cwd):
                    self.cwd = new_cwd
                break

    def teardown(self):
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1)
            except:
                try: self._proc.kill()
                except: pass
        if self._master_fd != -1:
            try: os.close(self._master_fd)
            except: pass


class TerminalSession(BaseModel):
    """
    Represents a persistent shell session for a specific context (Thread/Task).
    Holds the state (cwd, env) and the underlying PTY process.
    """
    cwd: str
    env: dict[str, str] = Field(default_factory=lambda: os.environ.copy())
    pty: Optional[PersistentTerminal] = Field(default=None)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def model_post_init(self, __context):
        if "TERM" not in self.env:
            self.env["TERM"] = "xterm-256color"

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get_pty(self, session_id: str) -> PersistentTerminal:
        if not self.pty:
            self.pty = PersistentTerminal(session_id, self.cwd, self.env)
        return self.pty


class TerminalManager:
    """
    Manages terminal sessions based on the current execution context.
    """
    _sessions: dict[str, TerminalSession] = {}

    @classmethod
    def _get_session_key(cls) -> str:
        ctx = ContextManager.current()
        return ctx.thread_id or ctx.request_id or "global"

    @classmethod
    def get_session(cls) -> TerminalSession:
        key = cls._get_session_key()
        if key not in cls._sessions:
            ctx = ContextManager.current()
            initial_cwd = ctx.working_directory or os.getcwd()
            cls._sessions[key] = TerminalSession(cwd=initial_cwd)

        return cls._sessions[key]

    @classmethod
    def run_command(cls, command: str, timeout: int = 60) -> tuple[str, str, int]:
        """
        Runs a command in a persistent PTY session.
        Returns (stdout, stderr, exit_code) for compatibility.
        """
        session = cls.get_session()
        key = cls._get_session_key()
        pty_sess = session.get_pty(key)
        
        command = command.strip()
        try:
            with session._lock:
                stdout, exit_code = pty_sess.run_command(command, timeout=timeout)
                # Sync session level CWD
                session.cwd = pty_sess.cwd
            return stdout, "", exit_code
        except Exception as e:
            logger.exception(f"[TerminalManager][{key}] System Error")
            return "", str(e), 1

    @classmethod
    def teardown_all(cls):
        for session in cls._sessions.values():
            if session.pty:
                session.pty.teardown()
        cls._sessions.clear()


# Global Accessor
terminal_manager = TerminalManager
