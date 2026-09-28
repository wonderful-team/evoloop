import asyncio
import logging
import subprocess

from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class CommandResult(DynamicBaseModel):
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        """Combined output or just stdout usually preferred."""
        return self.stdout.strip()


async def run_async_command(cmd: str | list[str], cwd: str | None = None, timeout: float | None = None) -> CommandResult:
    """
    Run an asynchronous subprocess command.
    """
    try:
        # Determine shell usage
        if isinstance(cmd, str):
            program = cmd
            create_proc = asyncio.create_subprocess_shell
            args = []
        else:
            create_proc = asyncio.create_subprocess_exec
            program = cmd[0]
            args = cmd[1:]

        import os
        import signal

        preexec = getattr(os, "setsid", None)
        extra_kwargs = {"preexec_fn": preexec} if preexec else {}

        if isinstance(cmd, str):
            process = await create_proc(
                program,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                **extra_kwargs,
            )
        else:
            process = await create_proc(
                program,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                **extra_kwargs,
            )

        try:
            if timeout:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            else:
                stdout, stderr = await process.communicate()
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            try:
                if preexec and process.pid:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
            except Exception:
                pass
            if isinstance(exc, asyncio.CancelledError):
                raise
            return CommandResult(-1, "", "Command timed out")

        return CommandResult(
            returncode=process.returncode if process.returncode is not None else -1,
            stdout=stdout.decode().strip() if stdout else "",
            stderr=stderr.decode().strip() if stderr else "",
        )

    except (
        subprocess.SubprocessError,
        OSError,
        TypeError,
        ValueError,
        asyncio.TimeoutError,
    ) as e:
        logger.exception(f"Async command failed: {e}")
        return CommandResult(-1, "", str(e))
