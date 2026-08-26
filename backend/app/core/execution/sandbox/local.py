import asyncio
import logging
import os
import shutil
import signal

from app.core.execution.sandbox.base import Sandbox, SandboxProcess

logger = logging.getLogger(__name__)


def _terminate_process_group(process: asyncio.subprocess.Process) -> None:
    """Gracefully terminate the whole process group of a subprocess."""
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass


def _kill_process_group(process: asyncio.subprocess.Process) -> None:
    """Force-kill the whole process group of a subprocess."""
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass


def _start_streaming(
    process: asyncio.subprocess.Process,
    *,
    on_output,
    stdout_buf: list[str] | None,
    stderr_buf: list[str] | None,
    read_timeout: float,
) -> asyncio.Task:
    """Stream process output into ``on_output`` (and optional buffers). Returns read_task."""

    async def read_stream(stream, is_stderr=False):
        prefix = "[stderr] " if is_stderr else ""
        while True:
            try:
                line = await asyncio.wait_for(stream.readline(), timeout=read_timeout)
                if not line:
                    break
                decoded_line = line.decode("utf-8", errors="replace")
                if is_stderr:
                    if stderr_buf is not None:
                        stderr_buf.append(decoded_line)
                elif stdout_buf is not None:
                    stdout_buf.append(decoded_line)

                if on_output is not None:
                    on_output(prefix + decoded_line.rstrip() + "\n")
            except asyncio.TimeoutError:
                if process.returncode is not None:
                    break
                continue

    async def gather_streams():
        await asyncio.gather(
            read_stream(process.stdout, is_stderr=False),
            read_stream(process.stderr, is_stderr=True),
        )

    return asyncio.create_task(gather_streams())


class LocalSandboxProcess(SandboxProcess):
    """Handle to a host subprocess spawned with ``setsid`` (own process group)."""

    def __init__(self, process: asyncio.subprocess.Process, read_task: asyncio.Task):
        self._process = process
        self._read_task = read_task

    @property
    def pid(self) -> int | None:
        return self._process.pid

    async def wait(self, timeout: float) -> int:
        exit_code = await asyncio.wait_for(self._process.wait(), timeout=timeout)
        try:
            await asyncio.wait_for(self._read_task, timeout=5.0)
        except asyncio.TimeoutError:
            pass
        return exit_code

    def terminate(self) -> None:
        _terminate_process_group(self._process)

    def kill(self) -> None:
        _kill_process_group(self._process)


class LocalSandbox(Sandbox):
    """
    Executes commands directly on the host machine as fresh subprocesses.
    WARNING: No OS-level isolation — commands run with full user privileges.
    """

    async def spawn(
        self,
        command: str,
        *,
        working_dir: str | None = None,
        on_output=None,
        stdout_buf: list[str] | None = None,
        stderr_buf: list[str] | None = None,
    ) -> SandboxProcess:
        wrapped = f"cd {working_dir} && {command}" if working_dir else command

        process = await asyncio.create_subprocess_shell(
            wrapped,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=os.setsid,
        )
        read_task = _start_streaming(
            process,
            on_output=on_output,
            stdout_buf=stdout_buf,
            stderr_buf=stderr_buf,
            read_timeout=0.5,
        )
        return LocalSandboxProcess(process, read_task)

    def upload_file(self, local_path: str, remote_path: str) -> None:
        # Local FS is shared, no-op or copy if paths differ
        if local_path != remote_path:
            try:
                shutil.copy2(local_path, remote_path)
            except Exception as e:
                logger.exception(f"Failed to copy local file: {e}")
                raise

    def download_file(self, remote_path: str, local_path: str) -> None:
        if local_path != remote_path:
            try:
                shutil.copy2(remote_path, local_path)
            except Exception as e:
                logger.exception(f"Failed to copy local file: {e}")
                raise

    def teardown(self) -> None:
        # Nothing to tear down for local shell
        pass
