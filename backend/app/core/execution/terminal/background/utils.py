"""Shared utilities for the execution subpackage."""

import logging

from app.core.context import ContextManager
from app.core.engine.message.native_classes import RunnableConfig
from app.utils.controller_response import ControllerResponse
from app.utils.template import render_template

logger = logging.getLogger(__name__)

MAX_OUTPUT_LINES = 1000


def get_thread_id(config: RunnableConfig | None) -> str:
    if config and "configurable" in config:
        thread_id = config["configurable"].get("thread_id")
        if thread_id:
            return thread_id

    ctx = ContextManager.current()
    return ctx.thread_id or ctx.request_id or "default"


def format_command_result(stdout: str, stderr: str, returncode: int, command: str = "") -> str:
    if stdout.count("\n") + stderr.count("\n") > MAX_OUTPUT_LINES:
        stdout_lines = stdout.split("\n")
        stderr_lines = stderr.split("\n")

        truncated_stdout = "\n".join(stdout_lines[:900])
        truncated_stderr = "\n".join(stderr_lines[:100])

        status_msg = "Command Completed (Output Truncated)."
        output_details = (
            f"STDOUT (First 900 lines):\n{truncated_stdout}"
            f"\n\nSTDERR (First 100 lines):\n{truncated_stderr}"
        )

        warning = (
            f"\n\n⚠️ WARNING: Output truncated to {MAX_OUTPUT_LINES} lines.\n"
            "Tip: Use redirection (e.g., `cmd > out.txt`) or `grep` to manage large outputs."
        )

        return ControllerResponse.success(status_msg, details=output_details + warning)

    status_msg = "Command Succeeded." if returncode == 0 else f"Command Failed (Exit Code {returncode})."

    try:
        output_details = render_template(
            "common/report/tool_outputs.prompt.j2",
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
        )
    except Exception:
        output_details = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"

    if returncode != 0:
        return ControllerResponse.error(status_msg, details=output_details)

    return ControllerResponse.success(status_msg, details=output_details)
