import asyncio
import logging
import os
import signal
import time
from typing import Any, Annotated, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.context import ContextManager
from app.core.tools import evoloop_tool, get_working_directory
from app.core.tools.background import task_manager, TaskType, TaskStatus, CreateBackgroundTaskRequest
from app.utils import ControllerResponse, SkillResponse, render_template

logger = logging.getLogger(__name__)


# Dangerous patterns that should be blocked
_BLOCKED_PATTERNS = [
    # Attempts to write to common system directories
    "> /etc/", "> /usr/", "> /bin/", "> /sbin/", "> /lib",
    # Attempts to modify system files
    "rm -rf /", "rm -rf /*", "> ~/.bashrc", "> ~/.zshrc",
    # Attempts to write outside workspace using relative escapes
    ".. /", "../ /", 
]


def _is_dangerous_command(command: str) -> tuple[bool, str]:
    """
    Check if a command contains dangerous patterns.
    Returns (is_dangerous, reason).
    """
    cmd_lower = command.lower()
    
    for pattern in _BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return True, f"Command contains blocked pattern: {pattern}"
    
    # Check for attempts to write to Desktop, Documents, Downloads in global mode
    # This prevents bypassing file write restrictions via shell redirection
    ctx = ContextManager.current()
    home_dir = os.path.expanduser("~")
    restricted_dirs = [
        os.path.join(home_dir, "Desktop"),
        os.path.join(home_dir, "Documents"), 
        os.path.join(home_dir, "Downloads"),
        os.path.join(home_dir, "Desktop"),
    ]
    
    # Check for shell redirection to restricted paths
    if ">" in command or ">>" in command:
        for restricted in restricted_dirs:
            if restricted in command or restricted.replace(home_dir, "~") in command:
                return True, f"Cannot write to {restricted} using execute_command. Use write_file tool instead."
    
    return False, ""


async def _execute_command(command: str, config: RunnableConfig | None = None) -> tuple[str, str, int]:
    """
    Internal function to execute a shell command.
    Used by execute_command tool and other internal operations.
    
    Commands are executed within the working directory context.
    In global mode, uses WORKSPACE_ROOT as the working directory.
    
    Returns:
        tuple: (stdout, stderr, returncode)
    """
    logger.info(f"Execution [Command]: {command}")
    
    # Security check for dangerous commands
    is_dangerous, reason = _is_dangerous_command(command)
    if is_dangerous:
        logger.warning(f"Blocked dangerous command: {command}")
        return "", f"Security Error: {reason}", 1

    try:
        from app.core.execution import SandboxFactory
        from app.infrastructure.config.service import SystemConfigService
        
        # Determine working directory
        # In global mode, use WORKSPACE_ROOT to ensure commands run in a safe location
        ctx = ContextManager.current()
        working_dir = get_working_directory(config)
        
        if ctx.project_id == 0 or (ctx.project_id is None and working_dir == "."):
            workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
            if workspace_root:
                working_dir = workspace_root
                logger.info(f"Global mode: Using WORKSPACE_ROOT as working directory: {working_dir}")

        sandbox = SandboxFactory.get_sandbox()
        
        # Prepend cd command to ensure command runs in correct directory
        # This is a soft enforcement - sophisticated escapes are still possible
        # but this prevents accidental writes to wrong locations
        if working_dir and working_dir != ".":
            # Use subshell to isolate directory change
            wrapped_command = f"cd {working_dir} && {command}"
        else:
            wrapped_command = command

        # Run via Sandbox (handles stateful CWD/ENV if using LocalSandbox)
        stdout, stderr, returncode = await asyncio.to_thread(sandbox.run_command, wrapped_command)
        
        return stdout, stderr, returncode

    except Exception as e:
        logger.error(f"Command execution error: {e}")
        return "", str(e), -1


MAX_OUTPUT_LINES = 1000


def _format_command_result(stdout: str, stderr: str, returncode: int, command: str = "") -> str:
    """Format command execution result for display."""
    # Output budget check
    # total_lines is an estimate for quick decision
    if stdout.count('\n') + stderr.count('\n') > MAX_OUTPUT_LINES:
        # Truncate while keeping a bit of both if possible
        # Simple approach: truncate total string
        stdout_lines = stdout.split('\n')
        stderr_lines = stderr.split('\n')

        # Give stdout more budget (900 lines) and stderr (100 lines) as a heuristic
        truncated_stdout = '\n'.join(stdout_lines[:900])
        truncated_stderr = '\n'.join(stderr_lines[:100])

        status_msg = "Command Completed (Output Truncated)."
        output_details = f"STDOUT (First 900 lines):\n{truncated_stdout}\n\nSTDERR (First 100 lines):\n{truncated_stderr}"

        warning = f"\n\n⚠️ WARNING: Output truncated to {MAX_OUTPUT_LINES} lines.\n"
        warning += "Tip: Use redirection (e.g., `cmd > out.txt`) or `grep` to manage large outputs."

        return ControllerResponse.success(status_msg, details=output_details + warning)

    status_msg = "Command Succeeded." if returncode == 0 else f"Command Failed (Exit Code {returncode})."

    try:
        output_details = render_template(
            "common/report/tool_outputs.prompt.j2",
            stdout=stdout,
            stderr=stderr,
            returncode=returncode
        )
    except Exception:
        # Fallback if template rendering fails
        output_details = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"

    if returncode == 0:
        return ControllerResponse.success(status_msg, details=output_details)
    else:
        return ControllerResponse.error(status_msg, details=output_details)


def _get_thread_id(config: Optional[RunnableConfig]) -> str:
    """Extract thread_id from config or context."""
    if config and "configurable" in config:
        thread_id = config["configurable"].get("thread_id")
        if thread_id:
            return thread_id
    
    ctx = ContextManager.current()
    return ctx.thread_id or ctx.request_id or "default"


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.execute_command"
)
async def execute_command(
    command: str,
    background: bool = False,
    timeout: int = 60,
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    Execute a shell command (e.g., 'pytest', 'npm install', 'ls -la', 'git status').

    This is your primary tool for navigating the OS, running scripts, building projects,
    and executing standard operating procedures including Git operations.

    In global mode, commands are executed within WORKSPACE_ROOT for safety.
    Use dedicated file tools for file operations rather than shell redirection.

    Output Limit: Maximum 1000 lines of stdout/stderr per call.
    For larger outputs, redirect to file or use background mode.

    WARNING: Use dedicated tools for standard operations when available:
    - File Editing -> Use `edit_file` / `write_file`.
    - File Reading -> Use `read_file`.
    - Directory Operations -> Use `execute_command` (mkdir, rm, mv) or `list_directory`.

    Args:
        command: The shell command to execute
        background: If True, run in background and return task_id immediately.
                   Use for long-running commands like builds (npm run build, docker build).
        timeout: Maximum execution time in seconds (default: 60, max: 3600).
                For background tasks, this is the background timeout.

    Examples:
        # Quick commands (default)
        execute_command(command="git status")

        # Long-running build (background mode)
        execute_command(command="npm run build", background=True, timeout=300)

        # Docker build
        execute_command(command="docker build -t myapp .", background=True, timeout=600)

        # Large output - redirect to file
        execute_command(command="cat large.log > /tmp/large.log")
        read_file(path="/tmp/large.log", start_line=1, end_line=1000)
    """
    # Validate timeout
    timeout = min(max(timeout, 10), 3600)  # Clamp between 10s and 1 hour
    
    if background:
        # Background mode: create task and return immediately
        return await _execute_in_background(command, timeout, config)
    else:
        # Smart mode: try sync first, auto-extend if needed
        return await _execute_smart(command, timeout, config)


async def _execute_in_background(
    command: str, 
    timeout: int, 
    config: Optional[RunnableConfig]
) -> str:
    """
    Execute command in background mode.
    Creates a task and returns immediately with task_id.
    """
    thread_id = _get_thread_id(config)
    
    # Create background task
    task = await task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title=f"执行: {command[:60]}{'...' if len(command) > 60 else ''}",
            description=f"命令: {command}",
            tool_name="execute_command",
            thread_id=thread_id,
            timeout_seconds=timeout,
        )
    )

    # Start execution in background
    asyncio.create_task(_run_command_background(task, command, timeout, config))
    
    return (
        "Background task started\n\n"
        f"任务ID: `{task.task_id}`\n"
        f"命令: `{command}`\n"
        f"超时: {timeout}秒\n\n"
        f"查询状态: `query_command_status('{task.task_id}')`\n"
        f"取消任务: `cancel_command('{task.task_id}')`"
    )


async def _run_command_background(
    task, 
    command: str, 
    timeout: int,
    config: Optional[RunnableConfig]
):
    """Run command in background and update task status."""
    try:
        # Determine working directory
        ctx = ContextManager.current()
        working_dir = get_working_directory(config)
        
        if ctx.project_id == 0 or (ctx.project_id is None and working_dir == "."):
            from app.infrastructure.config.service import SystemConfigService
            workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
            if workspace_root:
                working_dir = workspace_root
        
        # Wrap command with cd
        if working_dir and working_dir != ".":
            wrapped_command = f"cd {working_dir} && {command}"
        else:
            wrapped_command = command
        
        # Start process
        process = await asyncio.create_subprocess_shell(
            wrapped_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=os.setsid,  # Create new process group for clean termination
        )
        
        # Mark as started
        await task_manager.start_task(task.task_id, process.pid)
        
        # Setup cancel callback
        def cancel_callback():
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass  # Process already exited
        
        task.set_cancel_callback(cancel_callback)
        
        # Read output
        async def read_stream(stream, is_stderr=False):
            prefix = "[stderr] " if is_stderr else ""
            while True:
                try:
                    line = await asyncio.wait_for(stream.readline(), timeout=1.0)
                    if not line:
                        break
                    output = prefix + line.decode('utf-8', errors='replace').rstrip()
                    task_manager.append_output(task.task_id, output)
                except asyncio.TimeoutError:
                    # Check if process still running
                    if process.returncode is not None:
                        break
                    continue
        
        # Read both streams concurrently
        await asyncio.gather(
            read_stream(process.stdout, is_stderr=False),
            read_stream(process.stderr, is_stderr=True),
        )
        
        # Wait for completion with timeout
        try:
            exit_code = await asyncio.wait_for(process.wait(), timeout=timeout)
            
            if exit_code == 0:
                await task_manager.complete_task(task.task_id, result={"exit_code": 0})
            else:
                await task_manager.fail_task(
                    task.task_id, 
                    error=f"Command exited with code {exit_code}"
                )
        except asyncio.TimeoutError:
            # Kill the process group
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            await task_manager.timeout_task(task.task_id)
            
    except Exception as e:
        logger.error(f"Background command error: {e}", exc_info=True)
        await task_manager.fail_task(task.task_id, error=str(e))


async def _execute_smart(
    command: str, 
    timeout: int, 
    config: Optional[RunnableConfig]
) -> str:
    """
    Smart execution mode:
    1. Try to execute with initial timeout (60s)
    2. If still running, give periodic feedback to agent
    3. If total timeout exceeded, suggest background mode
    """
    thread_id = _get_thread_id(config)
    
    # Phase 1: Quick execution (up to 60s or specified timeout, whichever is smaller)
    quick_timeout = min(timeout, 60)
    
    try:
        # Try quick execution
        stdout, stderr, returncode = await _execute_command_with_timeout(
            command, quick_timeout, config
        )
        return _format_command_result(stdout, stderr, returncode, command=command)
        
    except asyncio.TimeoutError:
        # Command is taking longer than quick_timeout
        # Create a background task to continue execution
        
        if timeout <= quick_timeout:
            # No more time allowed, fail
            return (
                f"Command execution timeout ({quick_timeout}s)\n\n"
                f"命令: `{command}`\n\n"
                f"建议: 此命令可能需要更长时间，请使用后台模式:\n"
                f"`execute_command(command='{command}', background=True, timeout=300)`"
            )
        
        # Continue in background-like mode but with agent feedback
        task = await task_manager.create_task(
            CreateBackgroundTaskRequest(
                task_type=TaskType.COMMAND,
                title=f"执行: {command[:60]}{'...' if len(command) > 60 else ''}",
                description=f"命令: {command}",
                tool_name="execute_command",
                thread_id=thread_id,
                timeout_seconds=timeout,
            )
        )
        
        # Start process
        ctx = ContextManager.current()
        working_dir = get_working_directory(config)
        
        if ctx.project_id == 0 or (ctx.project_id is None and working_dir == "."):
            from app.infrastructure.config.service import SystemConfigService
            workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
            if workspace_root:
                working_dir = workspace_root
        
        if working_dir and working_dir != ".":
            wrapped_command = f"cd {working_dir} && {command}"
        else:
            wrapped_command = command
        
        process = await asyncio.create_subprocess_shell(
            wrapped_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=os.setsid,
        )
        
        await task_manager.start_task(task.task_id, process.pid)
        
        # Setup cancel callback
        def cancel_callback():
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        
        task.set_cancel_callback(cancel_callback)
        
        # Collect output for remaining time
        remaining_time = timeout - quick_timeout
        start_time = time.time()
        
        async def read_with_timeout():
            async def read_stream(stream, is_stderr=False):
                prefix = "[stderr] " if is_stderr else ""
                while True:
                    try:
                        line = await asyncio.wait_for(stream.readline(), timeout=1.0)
                        if not line:
                            break
                        output = prefix + line.decode('utf-8', errors='replace').rstrip()
                        task_manager.append_output(task.task_id, output)
                    except asyncio.TimeoutError:
                        if process.returncode is not None:
                            break
                        continue
            
            await asyncio.gather(
                read_stream(process.stdout, is_stderr=False),
                read_stream(process.stderr, is_stderr=True),
            )
        
        # Wait for completion or timeout
        try:
            await asyncio.wait_for(read_with_timeout(), timeout=remaining_time)
            exit_code = await asyncio.wait_for(process.wait(), timeout=5)
            
            if exit_code == 0:
                await task_manager.complete_task(task.task_id, result={"exit_code": 0})
                output = task.get_recent_output(n=100)
                return (
                    f"Command execution completed (elapsed: {task.elapsed_seconds}s)\n\n"
                    f"最后输出:\n```\n{output}\n```"
                )
            else:
                await task_manager.fail_task(task.task_id, error=f"Exit code: {exit_code}")
                output = task.get_recent_output(n=50)
                return (
                    f"Command execution failed (exit code: {exit_code})\n\n"
                    f"最后输出:\n```\n{output}\n```"
                )
                
        except asyncio.TimeoutError:
            # Total timeout exceeded
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            await task_manager.timeout_task(task.task_id)
            
            output = task.get_recent_output(n=30)
            return (
                f"Command execution timeout (total limit: {timeout}s)\n\n"
                f"命令仍在后台运行，但已超过最大等待时间。\n"
                f"任务ID: `{task.task_id}`\n\n"
                f"最近输出:\n```\n{output}\n```\n\n"
                f"查询完整状态: `query_command_status('{task.task_id}')`"
            )


async def _execute_command_with_timeout(
    command: str, 
    timeout: int, 
    config: Optional[RunnableConfig]
) -> tuple[str, str, int]:
    """
    Execute command with specified timeout.
    Raises asyncio.TimeoutError if timeout exceeded.
    """
    # Security check
    is_dangerous, reason = _is_dangerous_command(command)
    if is_dangerous:
        return "", f"Security Error: {reason}", 1
    
    # Determine working directory
    ctx = ContextManager.current()
    working_dir = get_working_directory(config)
    
    if ctx.project_id == 0 or (ctx.project_id is None and working_dir == "."):
        from app.infrastructure.config.service import SystemConfigService
        workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
        if workspace_root:
            working_dir = workspace_root
    
    if working_dir and working_dir != ".":
        wrapped_command = f"cd {working_dir} && {command}"
    else:
        wrapped_command = command
    
    # Run with timeout
    process = await asyncio.create_subprocess_shell(
        wrapped_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout
        )
        return (
            stdout.decode('utf-8', errors='replace'),
            stderr.decode('utf-8', errors='replace'),
            process.returncode
        )
    except asyncio.TimeoutError:
        # Kill process on timeout
        try:
            process.kill()
            await process.wait()
        except (OSError, ProcessLookupError):
            pass
        raise


@evoloop_tool(
    is_pollable=True,
    is_hidden=True,  # Internal polling for background commands, not user-facing
    summary_template="evoloop.tool_summary.query_command_status"
)
async def query_command_status(
    task_id: str,
    include_output: bool = True,
    output_lines: int = 50,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Query the status of a background command task.
    
    Use this to check the progress or result of a command that was started
    with background=True.
    
    Args:
        task_id: The task ID returned by execute_command(background=True)
        include_output: Whether to include recent output (default: True)
        output_lines: Number of output lines to include (default: 50, max: 200)
    
    Examples:
        query_command_status("cmd-a1b2c3d4")
        query_command_status("cmd-a1b2c3d4", output_lines=100)
    """
    task = task_manager.get_task(task_id)
    
    if not task:
        return f"Task not found: `{task_id}`\n\nPossible reasons:\n1. Wrong task ID\n2. Task completed over 24 hours ago (auto-cleaned)\n3. Task belongs to another conversation"
    
    # Status labels
    status_labels = {
        TaskStatus.PENDING: "PENDING",
        TaskStatus.RUNNING: "RUNNING",
        TaskStatus.COMPLETED: "COMPLETED",
        TaskStatus.FAILED: "FAILED",
        TaskStatus.CANCELLED: "CANCELLED",
        TaskStatus.TIMEOUT: "TIMEOUT",
    }
    status_label = status_labels.get(task.status, task.status.value)
    
    # Build response
    lines = [
        f"Status: {status_label}",
        "",
        f"任务ID: `{task.task_id}`",
        f"命令: `{task.title}`",
        f"耗时: {task.elapsed_seconds}秒",
    ]
    
    if task.status == TaskStatus.RUNNING:
        lines.append(f"进程ID: {task.process_id}")
    
    lines.append("")
    
    # Include output if requested
    if include_output and task.output_buffer:
        n = min(output_lines, 200)
        output = task.get_recent_output(n)
        lines.append(f"最近输出（最后{n}行）:")
        lines.append("```")
        lines.append(output if output else "（无输出）")
        lines.append("```")
        lines.append("")
    
    # Result or error
    if task.status == TaskStatus.COMPLETED:
        lines.append("Command execution successful")
        if task.result:
            lines.append(f"结果: {task.result}")
    elif task.status == TaskStatus.FAILED:
        lines.append(f"Execution failed: {task.error_message or 'unknown error'}")
    elif task.status == TaskStatus.CANCELLED:
        lines.append("Task cancelled")
    elif task.status == TaskStatus.TIMEOUT:
        lines.append("Task timeout")
    elif task.status == TaskStatus.RUNNING:
        lines.append("Note: Task is still running, query again in 10 seconds for latest status")
    
    return "\n".join(lines)


@evoloop_tool(
    is_pollable=True,
    summary_template="evoloop.tool_summary.cancel_command"
)
async def cancel_command(
    task_id: str,
    force: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Cancel a running background command.
    
    Args:
        task_id: The task ID to cancel
        force: If True, use SIGKILL immediately instead of SIGTERM (default: False)
    
    Examples:
        cancel_command("cmd-a1b2c3d4")
        cancel_command("cmd-a1b2c3d4", force=True)  # Force kill
    """
    task = task_manager.get_task(task_id)
    
    if not task:
        return f"Task not found: `{task_id}`"
    
    if task.is_completed:
        return (
            "Task already completed, cannot cancel\n\n"
            f"状态: {task.status.value}\n"
            f"完成时间: {task.completed_at}"
        )
    
    # Try to cancel
    success = await task_manager.cancel_task(task_id)
    
    if success:
        if force and task.process_id:
            # Force kill if requested
            try:
                os.killpg(os.getpgid(task.process_id), signal.SIGKILL)
            except ProcessLookupError:
                pass  # Process already gone
        
        return (
            "Task cancelled\n\n"
            f"任务ID: `{task_id}`\n"
            f"命令: `{task.title}`"
        )
    else:
        return f"Cannot cancel task (current status: {task.status.value})"


@evoloop_tool(
    is_pollable=True,
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.run_macro"
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

    WHEN TO USE:
    - After `search_skills` returns a match with `execution_mode = "deterministic"`.
    - When the user explicitly asks you to replay a recorded skill.
    - When you want to repeat a previously successful multi-step automation.

    WHEN NOT TO USE:
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
    from app.models.learning import LearnedSkill
    from sqlalchemy import select, func

    # 1. Resolve thread_id from LangGraph config
    thread_id = "default"
    if config:
        cfgable = config.get("configurable", {}) if isinstance(config, dict) else getattr(config, "configurable", {})
        thread_id = cfgable.get("thread_id", "default") or "default"

    # 2. Load skill from DB
    skill = None
    try:
        async with session_scope() as db:
            if skill_id is not None:
                skill = await db.get(LearnedSkill, skill_id)
            elif skill_name:
                stmt = select(LearnedSkill).where(
                    func.lower(LearnedSkill.name) == skill_name.lower(),
                    LearnedSkill.is_active == True,
                )
                result = await db.execute(stmt)
                skill = result.scalar_one_or_none()
    except Exception as e:
        return ControllerResponse.error(
            f"Failed to look up skill '{skill_name or skill_id}'",
            details=str(e)
        )

    if not skill:
        identifier = f"id={skill_id}" if skill_id else f"name='{skill_name}'"
        return ControllerResponse.not_found(identifier, item_type="skill")

    # 3. Parse and validate macro script (now stored as YAML string)
    macro_script = None
    if skill.macro_script:
        from app.utils.yaml import macro_from_yaml
        try:
            macro_script = macro_from_yaml(skill.macro_script)
        except Exception as e:
            return ControllerResponse.error(
                f"Failed to parse macro YAML for skill '{skill.name}'",
                details=str(e)
            )

    if not macro_script or not isinstance(macro_script, list) or len(macro_script) == 0:
        mode = skill.execution_mode or "agentic"
        return ControllerResponse.error(
            f"Skill '{skill.name}' has no macro script.",
            details=f"Mode: {mode}\nInstructions: {skill.instructions or 'None'}",
            note="This skill requires agentic execution."
        )

    if skill.execution_mode != "deterministic":
        return ControllerResponse.error(
            f"Skill '{skill.name}' is not in deterministic mode.",
            details=f"Current mode: {skill.execution_mode}\nInstructions: {skill.instructions or 'None'}",
            note="Follow the SOP instructions above instead."
        )

    logger.info(
        f"[run_macro] Executing skill '{skill.name}' (id={skill.id}) "
        f"with {len(macro_script)} steps, params={params}"
    )
    
    # Pass metadata for the event advisor to use
    execution_params = params.copy() if params else {}
    execution_params["_skill_id"] = skill.id
    execution_params["_skill_name"] = skill.name
    
    result = await MacroService.run(
        thread_id=thread_id,
        script_input=macro_script,
        params=execution_params,
        skill=skill,
    )

    # 5. Format result using SkillResponse for consistency
    if result.get("success"):
        return SkillResponse.success(skill.name, result.get("extracted_data"))
    else:
        return SkillResponse.error(
            skill.name,
            result.get("message", "Unknown error"),
            fallback_context=result.get("fallback_context"),
            suggestions=result.get("suggestions", [])
        )
