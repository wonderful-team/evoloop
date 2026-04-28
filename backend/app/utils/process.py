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


def run_command(
    cmd: str | list[str],
    cwd: str | None = None,
    check: bool = False,
    timeout: float | None = None,
    env: dict | None = None,
) -> CommandResult:
    """
    Run a synchronous subprocess command.
    """
    if isinstance(cmd, str):
        # Shell=True if string provided? Or split?
        # Safer to force list, but sometimes shell convenience is needed.
        # Let's standardize: If list -> shell=False, If str -> shell=True
        shell = True
        args = cmd
    else:
        shell = False
        args = cmd

    try:
        logger.debug(f"Running command: {args} (cwd={cwd})")
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            shell=shell,
            timeout=timeout,
            env=env,
        )
        if check and result.returncode != 0:
            logger.warning(f"Command failed: {args}, stderr: {result.stderr}")
            # Raise or just return?
            # subprocess.run with check=True raises CalledProcessError.
            # But we want to return CommandResult generally.
            # If check=True, we manually raise to match standard lib expectation IF caller expects it.
            # But here, let's just return the result and let caller check .success
            pass

        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr
        )
    except (subprocess.SubprocessError, OSError, TypeError, ValueError) as e:
        logger.error(f"Command execution exception: {e}")
        return CommandResult(-1, "", str(e))


async def run_async_command(
    cmd: str | list[str],
    cwd: str | None = None,
    timeout: float | None = None
) -> CommandResult:
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

        logger.debug(f"Async running: {cmd} (cwd={cwd})")

        if isinstance(cmd, str):
            process = await create_proc(
                program,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
        else:
            process = await create_proc(
                program,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

        try:
            if timeout:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            else:
                stdout, stderr = await process.communicate()
        except asyncio.TimeoutError:
            process.kill()
            return CommandResult(-1, "", "Command timed out")

        return CommandResult(
            returncode=process.returncode if process.returncode is not None else -1,
            stdout=stdout.decode().strip() if stdout else "",
            stderr=stderr.decode().strip() if stderr else "",
        )

    except (subprocess.SubprocessError, OSError, TypeError, ValueError, asyncio.TimeoutError) as e:
        logger.error(f"Async command failed: {e}")
        return CommandResult(-1, "", str(e))
