import asyncio
import logging
from typing import Any, Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    summary_template="database_logger.tool_summary.bash"
)
async def bash(command: str) -> str:
    """
    Run a shell command (e.g., 'pytest', 'npm install', 'ls -la').

    This is your primary tool for navigating the OS, running scripts, building projects,
    and executing standard operating procedures.

    WARNING: Use dedicated tools for standard operations when available:
    - Version Control -> Use `manage_git` tools.
    - File Editing -> Use `edit_file` / `write_file`.
    - File Reading -> Use `read_file`.

    Only use this for execution tasks like running tests, builds, or scripts.
    """
    logger.info(f"Execution [Bash]: {command}")

    try:
        from app.core.execution import SandboxFactory

        sandbox = SandboxFactory.get_sandbox()

        # Run via Sandbox (handles stateful CWD/ENV if using LocalSandbox)
        stdout, stderr, returncode = await asyncio.to_thread(sandbox.run_command, command)

        output = ""
        if stdout:
            output += f"STDOUT:\n{stdout}\n"
        if stderr:
            output += f"STDERR:\n{stderr}\n"

        if returncode == 0:
            return f"Command Succeeded.\n{output}"
        else:
            return f"Command Failed (Exit Code {returncode}).\n{output}"

    except Exception as e:
        return f"Execution Error: {str(e)}"


@evoloop_tool(
    is_pollable=True,
    is_state_mutating=True,
    summary_template="database_logger.tool_summary.run_macro"
)
async def run_macro(
    skill_name: str | None = None,
    skill_id: int | None = None,
    params: dict[str, Any] | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Execute a learned macro skill by name or ID.

    Use this when you know a specific learned macro exists and you want to run it
    deterministically. This is more efficient and reliable than recreating steps
    from scratch using browser_control / desktop_control / mobile_control.

    ## When to use
    - After `search_skills` returns a match with `execution_mode = "deterministic"`.
    - When the user explicitly asks you to replay a recorded skill.
    - When you want to repeat a previously successful multi-step automation.

    ## When NOT to use
    - For open-ended tasks where adaptive reasoning is required (use tools directly).
    - When the skill returns `execution_mode = "agentic"` (follow its `markdown_sop` instead).

    Args:
        skill_name: Exact name of the skill to execute. Perform a case-insensitive DB lookup.
                    Use the name returned by `search_skills`.
        skill_id:   Skill ID (integer primary key). Use if you have the exact ID from
                    `search_skills`. Takes precedence over skill_name when both are given.
        params:     Runtime parameter dict to inject into the macro steps,
                    e.g. {"query": "iPhone 15", "target_url": "https://example.com"}.
                    These map to `{{parameters.query}}` placeholders in the macro steps.
        thread_id:  The current conversation thread ID (injected automatically by the
                    framework; you do not need to pass this manually).

    Returns:
        A string summary of execution result, including extracted_data if any EXTRACT
        steps were present.

    Example:
        # After search_skills returns skill_id=42, execution_mode="deterministic":
        result = await run_macro(skill_id=42, params={"keyword": "机器学习"})
    """
    from app.core.execution.macro.service import MacroService
    from app.infrastructure.database.sql.database import session_scope
    from sqlalchemy import select, func

    # REMOVED: LearnedSkill model moved to cloud
    # Client mode should fetch skills from cloud API
    # For now, return a message indicating cloud API should be used
    logger.debug(f"[run_macro] Skill lookup for '{skill_name}' (id={skill_id}) - learning module moved to cloud")
    return "[Client Mode] Skill execution via cloud API not yet implemented. Please use local macro execution."

    # 5. Format result
    if result.get("success"):
        extracted = result.get("extracted_data", {})
        summary = f"✅ Skill '{skill.name}' completed successfully."
        if extracted:
            lines = [f"  - {k}: {v}" for k, v in extracted.items() if v]
            summary += "\n\nExtracted Data:\n" + "\n".join(lines)
        return summary
    else:
        msg = result.get("message", "Unknown error")
        fallback = result.get("fallback_context")
        suggestions = result.get("suggestions", [])
        
        output = f"❌ Skill '{skill.name}' failed: {msg}"
        if fallback:
            failed_step = fallback.get("failed_step", {})
            output += f"\n\nFailed step: {failed_step.get('description') or failed_step.get('event_type')}"
            output += f"\nError: {fallback.get('error_message')}"

    # TODO: Implement cloud API lookup for skills in client mode
    # For now, this function returns a placeholder message
