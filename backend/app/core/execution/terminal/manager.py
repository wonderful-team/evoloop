import codecs
import logging
import os
import pty
import select
import subprocess
import termios
import threading
import time
import uuid
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from app.core.context.manager import ContextManager

logger = logging.getLogger(__name__)


def _make_stream_filter(marker: bytes) -> Callable[[bytes], bytes]:
    """
    Returns a stateful feed() function that strips the given marker bytes
    (and everything that follows) from a streaming byte sequence.

    The filter handles the case where the marker spans across multiple chunks
    by keeping a sliding overlap window at the tail of the pending buffer.
    """
    pending = bytearray()

    def feed(chunk: bytes) -> bytes:
        nonlocal pending
        pending.extend(chunk)

        # Fast path: full marker found in buffer → safe to emit everything before it
        idx = pending.find(marker)
        if idx != -1:
            safe = bytes(pending[:idx])
            # Keep the marker and tail so the caller can parse the exit code
            del pending[:idx]
            return safe

        # Slow path: check whether the tail of pending is a *prefix* of the marker.
        # We must not emit those bytes yet because the next chunk might complete the marker.
        overlap = 0
        for i in range(min(len(pending), len(marker) - 1), 0, -1):
            if bytes(pending[-i:]) == marker[:i]:
                overlap = i
                break

        if overlap > 0:
            safe = bytes(pending[:-overlap])
            del pending[:-overlap]
        else:
            safe = bytes(pending)
            pending.clear()

        return safe

    return feed


class PersistentTerminal(BaseModel):
    """
    Manages a long-running interactive shell process via PTY with robust signal tracking.
    """
    session_id: str
    cwd: str
    env: dict[str, str]

    _master_fd: int = -1
    _proc: subprocess.Popen | None = None

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
        shell_env["TERM"] = "xterm-256color"
        # We use a blank PS1 since we use unique SIG markers for status
        shell_env["PS1"] = ""
        # Silence macOS bash deprecation warning
        shell_env["BASH_SILENCE_DEPRECATION_WARNING"] = "1"

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

        # Initial stabilization wait and drain any startup banner/warning bytes
        time.sleep(0.2)
        while True:
            r, _, _ = select.select([self._master_fd], [], [], 0.0)
            if r:
                try:
                    os.read(self._master_fd, 4096)
                except OSError:
                    break
            else:
                break
        logger.debug(f"[PTY][{self.session_id}] Shell started (PID: {self._proc.pid}) at {self.cwd}")

    def run_command(
        self,
        command: str,
        timeout: int = 60,
        on_output: Callable[[str], None] | None = None,
    ) -> tuple[str, int]:
        """Execute a command synchronously and return (output, exit_code).

        Args:
            command:   Shell command string to execute.
            timeout:   Maximum seconds to wait for the command to finish.
            on_output: Optional callback invoked with each decoded output chunk
                       in real-time (marker bytes are filtered out before
                       the callback fires).
        """
        if self._proc.poll() is not None:
            logger.warning(f"[PTY][{self.session_id}] Shell died. Restarting...")
            self._start_shell()

        # Generate a unique marker for this specific execution
        sig = str(uuid.uuid4())
        marker = f"EVO_SIG_DONE_{sig}_"
        marker_bytes = marker.encode()
        # Wrap command to echo status at the end
        # Use printf for reliable exit code capture: outputs "MARKER0\n" or "MARKER1\n"
        full_cmd = f"{command}\nprintf '{marker}%d\\n' $?\n"

        # Build per-call helpers for streaming (only when caller wants them)
        if on_output is not None:
            stream_filter = _make_stream_filter(marker_bytes)
            utf8_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

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

                    # Real-time streaming callback with marker filtering
                    if on_output is not None:
                        clean_bytes = stream_filter(chunk)
                        if clean_bytes:
                            text_chunk = utf8_decoder.decode(clean_bytes)
                            if text_chunk:
                                on_output(text_chunk)

                    # Look for the marker sequence
                    if marker_bytes in output:
                        # Check if we have the full signature including exit code and final newline
                        rest = output.split(marker_bytes)[1]
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

    def write_raw(self, data: bytes) -> None:
        """Write raw bytes directly to the PTY master fd.

        Used for interactive input (e.g. answering prompts, sending Ctrl+C,
        Tab completion) without going through the marker-based run_command
        protocol. This must NOT acquire the session lock because it is designed
        to be called *while* a run_command is in progress.
        """
        if self._master_fd == -1:
            raise OSError("PTY master fd is not open")
        os.write(self._master_fd, data)

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
            except (OSError, ProcessLookupError):
                try: self._proc.kill()
                except (OSError, ProcessLookupError): pass
        if self._master_fd != -1:
            try: os.close(self._master_fd)
            except OSError: pass


class TerminalSession(BaseModel):
    """
    Represents a persistent shell session for a specific context (Thread/Task).
    Holds the state (cwd, env) and the underlying PTY process.
    """
    cwd: str
    env: dict[str, str] = Field(default_factory=lambda: os.environ.copy())
    pty: PersistentTerminal | None = Field(default=None)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def model_post_init(self, __context):
        if "TERM" not in self.env:
            self.env["TERM"] = "xterm-256color"

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get_pty(self, session_id: str) -> PersistentTerminal:
        if not self.pty:
            self.pty = PersistentTerminal(session_id=session_id, cwd=self.cwd, env=self.env)
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
        from app.core.tools.base import get_working_directory
        current_cwd = get_working_directory()

        if key not in cls._sessions:
            cls._sessions[key] = TerminalSession(cwd=current_cwd)
        else:
            session = cls._sessions[key]
            if session.cwd != current_cwd:
                session.cwd = current_cwd
                if session.pty and session.pty._proc and session.pty._proc.poll() is None:
                    try:
                        os.write(session.pty._master_fd, f"cd {current_cwd}\n".encode())
                        session.pty.cwd = current_cwd
                    except Exception:
                        pass

        return cls._sessions[key]

    @classmethod
    def get_session_for_thread(cls, thread_id: str) -> TerminalSession | None:
        """Retrieve an existing session by thread_id without context injection.

        Used by API routes that know the thread_id explicitly (e.g. terminal/input).
        Returns None if no session exists yet for this thread.
        """
        return cls._sessions.get(thread_id)

    @classmethod
    def run_command(
        cls,
        command: str,
        timeout: int = 60,
        on_output: Callable[[str], None] | None = None,
    ) -> tuple[str, str, int]:
        """
        Runs a command in a persistent PTY session.
        Returns (stdout, stderr, exit_code) for compatibility.

        Args:
            command:   Shell command string to execute.
            timeout:   Maximum seconds to wait.
            on_output: Optional streaming callback; receives incremental decoded
                       text chunks as the command produces output.
        """
        session = cls.get_session()
        key = cls._get_session_key()
        pty_sess = session.get_pty(key)

        command = command.strip()
        try:
            with session._lock:
                stdout, exit_code = pty_sess.run_command(command, timeout=timeout, on_output=on_output)
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
