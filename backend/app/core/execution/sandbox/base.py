"""Abstract Base Class for Code Execution Sandboxes."""

from abc import ABC, abstractmethod
from collections.abc import Callable


class SandboxProcess(ABC):
    """
    Handle to a running sandboxed command.

    Encapsulates streamed output delivery and process control so the caller
    (runner) can wait for completion, cancel on timeout, or let a background
    task keep running across a quick-timeout boundary.
    """

    @property
    @abstractmethod
    def pid(self) -> int | None:
        """OS PID of the running process (None when not applicable, e.g. docker exec)."""

    @abstractmethod
    async def wait(self, timeout: float) -> int:
        """Wait for the command to exit within ``timeout`` seconds.

        Returns the exit code. Raises ``asyncio.TimeoutError`` if the command
        does not finish in time.
        """

    @abstractmethod
    def terminate(self) -> None:
        """Gracefully stop the command (SIGTERM for local, exec_kill for docker)."""

    @abstractmethod
    def kill(self) -> None:
        """Forcefully stop the command (SIGKILL for local, exec_kill for docker)."""


class Sandbox(ABC):
    """
    Isolation boundary for command execution.

    Implementations decide *where* commands run (fresh host subprocess, docker
    container) and how files are exchanged with the outside.
    """

    @abstractmethod
    async def spawn(
        self,
        command: str,
        *,
        working_dir: str | None = None,
        on_output: Callable[[str], None] | None = None,
        stdout_buf: list[str] | None = None,
        stderr_buf: list[str] | None = None,
    ) -> SandboxProcess:
        """
        Spawn a command for async streaming execution.

        Args:
            command: Raw command string (no working-directory wrapper).
            working_dir: Host working directory the command runs from. The
                sandbox translates it to its own layout (docker bind mount).
            on_output: Optional callback invoked with each decoded output chunk
                (``[stderr] `` prefixed for stderr lines) as it streams.
            stdout_buf: Optional buffer to capture raw stdout lines.
            stderr_buf: Optional buffer to capture raw stderr lines.

        Returns:
            A :class:`SandboxProcess` handle for waiting/cancelling.
        """
        pass

    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str) -> None:
        """
        Upload a file to the sandbox.
        For Docker bind-mounts, this might be a no-op or a copy.
        """
        pass

    @abstractmethod
    def download_file(self, remote_path: str, local_path: str) -> None:
        """
        Download a file from the sandbox.
        """
        pass

    @abstractmethod
    def teardown(self) -> None:
        """
        Cleanup resources (stop containers, etc.).
        """
        pass
