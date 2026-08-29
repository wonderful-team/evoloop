"""Bash step executor for the macro engine."""

import asyncio
import logging

from app.core.monitoring.activity import activity_monitor

logger = logging.getLogger(__name__)


class BashMixin:
    """Run shell commands as deterministic macro steps."""

    @classmethod
    async def _execute_bash_step(
        cls,
        thread_id: str,
        payload: dict,
        extracted_data: dict,
    ) -> None:
        """Execute a bash step, capturing stdout into ``extracted_data[key]``.

        The step payload expects:
          - command (str, required): shell command to run
          - key (str, default "bash_output"): key under which to store output
          - timeout (int|float, default 30): max seconds to wait
          - continue_on_error (bool, default False): store error instead of raising
        """
        command = payload.get("command")
        if not command or not isinstance(command, str):
            raise ValueError("Bash step requires a valid 'command' string")

        key = payload.get("key", "bash_output")
        if not isinstance(key, str):
            raise ValueError("Bash step 'key' must be a string")

        timeout = payload.get("timeout", 30)
        try:
            timeout = float(timeout)
            if timeout <= 0:
                timeout = 30.0
        except (TypeError, ValueError):
            timeout = 30.0

        continue_on_error = bool(payload.get("continue_on_error", False))

        display_command = command[:200].replace("\n", " ")
        logger.info(f"[{thread_id}] Bash step: {display_command}")
        await activity_monitor.log_event(
            "macro_thought",
            {"text": f"Running bash: {display_command}"},
            thread_id,
        )

        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"[{thread_id}] Bash step timed out after {timeout}s", exc_info=True
            )
            if process is not None:
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
            if continue_on_error:
                extracted_data[key] = f"Timeout after {timeout}s"
                return
            raise RuntimeError(f"Bash step timed out after {timeout}s")

        if stdout is None:
            stdout = b""
        if stderr is None:
            stderr = b""

        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")

        returncode = process.returncode if process else -1

        if returncode != 0:
            output = (
                f"Exit code {returncode}\nSTDOUT:\n{stdout_str}\nSTDERR:\n{stderr_str}"
            ).strip()
            logger.warning(
                f"[{thread_id}] Bash step failed with exit code {returncode}: {output[:200]}"
            )
            if continue_on_error:
                extracted_data[key] = output
                return
            raise ValueError(output)

        output = stdout_str
        if stderr_str.strip():
            output += f"\nSTDERR:\n{stderr_str}"

        logger.info(f"[{thread_id}] Bash step completed successfully")
        extracted_data[key] = output.strip()
