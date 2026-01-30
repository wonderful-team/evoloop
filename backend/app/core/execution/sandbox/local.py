import logging
import shutil

from app.core.execution.sandbox.base import Sandbox
from app.core.execution.terminal.manager import terminal_manager

logger = logging.getLogger(__name__)


class LocalSandbox(Sandbox):
    """
    Executes commands directly on the host machine using TerminalManager.
    WARNING: No isolation.
    """

    def run_command(self, command: str, timeout: int = 120) -> tuple[str, str, int]:
        # Delegate to the stateful TerminalManager
        return terminal_manager.run_command(command, timeout=timeout)

    def upload_file(self, local_path: str, remote_path: str) -> None:
        # Local FS is shared, no-op or copy if paths differ
        # Ideally, remote_path should be absolute.
        # If we really need to copy:
        if local_path != remote_path:
            try:
                shutil.copy2(local_path, remote_path)
            except Exception as e:
                logger.error(f"Failed to copy local file: {e}")
                raise

    def download_file(self, remote_path: str, local_path: str) -> None:
        # Same as upload
        if local_path != remote_path:
            try:
                shutil.copy2(remote_path, local_path)
            except Exception as e:
                logger.error(f"Failed to copy local file: {e}")
                raise

    def teardown(self) -> None:
        # Nothing to tear down for local shell
        pass
