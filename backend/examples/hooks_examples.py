"""
EvoLoop Hooks - Usage Examples

This file demonstrates how to use the enhanced hook system
with all the features inspired by Claude Code.
"""

import asyncio
from app.core.engine.hooks import (
    hook_system, HookEvent, HookContext, HookResult
)


# =============================================================================
# Example 1: Matcher Filtering (Regex patterns)
# =============================================================================

@hook_system.register(HookEvent.POST_TOOL_USE, matcher="^Write$|^Edit$")
async def auto_format_code(context: HookContext) -> HookResult:
    """
    Auto-format code after file writes.
    Only triggers for Write or Edit tools.
    """
    file_path = context.tool_input.get("path")
    if file_path and file_path.endswith(".py"):
        # Run black formatter
        import subprocess
        try:
            subprocess.run(["black", file_path], check=True, capture_output=True)
            return HookResult(success=True, message=f"Formatted {file_path}")
        except subprocess.CalledProcessError as e:
            return HookResult(success=False, message=f"Format failed: {e}")
    return HookResult(success=True)


@hook_system.register(HookEvent.POST_TOOL_USE, matcher="^Read$|^Glob$|^Grep$")
async def log_read_operations(context: HookContext) -> HookResult:
    """
    Log all read operations for analytics.
    Only triggers for read-only tools.
    """
    print(f"[ReadOp] {context.tool_name}: {context.tool_input}")
    return HookResult(success=True)


# =============================================================================
# Example 2: Security Gate (PreToolUse blocking)
# =============================================================================

@hook_system.register(HookEvent.PRE_TOOL_USE, matcher="^Bash$|^ExecuteCommand$")
async def security_gate(context: HookContext) -> HookResult:
    """
    Block dangerous shell commands.
    Can block execution by returning block=True.
    """
    command = context.tool_input.get("command", "")
    
    dangerous_patterns = [
        "rm -rf /",
        "rm -rf ~",
        "rm -rf /*",
        "sudo ",
        "mkfs",
        "dd if=",
        "> /etc/passwd",
        ":(){ :|:& };:",  # Fork bomb
    ]
    
    for pattern in dangerous_patterns:
        if pattern in command:
            return HookResult(
                success=False,
                block=True,
                message=f"🚫 Security: Dangerous command blocked: {pattern}"
            )
    
    # Check for .env file access
    if ".env" in command and "cat" not in command and "grep" not in command:
        return HookResult(
            success=False,
            block=True,
            message="🚫 Security: Direct .env modification blocked. Use manage_env tool."
        )
    
    return HookResult(success=True)


# =============================================================================
# Example 3: Quality Gate (Stop blocking)
# =============================================================================

@hook_system.register(HookEvent.STOP)
async def quality_gate(context: HookContext) -> HookResult:
    """
    Block session completion if quality checks fail.
    
    This is a powerful pattern for enforcing standards:
    - All tests must pass
    - Code coverage minimum
    - No lint errors
    - Documentation complete
    """
    blackboard = context.blackboard
    
    # Check test failures
    test_failures = blackboard.get("test_failures", [])
    if test_failures:
        return HookResult(
            success=False,
            block=True,
            message=f"❌ Tests failing ({len(test_failures)}). Fix before completing.\n"
                   f"Failures: {', '.join(test_failures[:3])}"
        )
    
    # Check lint errors
    lint_errors = blackboard.get("lint_errors", [])
    if lint_errors:
        return HookResult(
            success=False,
            block=True,
            message=f"❌ Lint errors ({len(lint_errors)}). Run formatter before completing."
        )
    
    # Check coverage
    coverage = blackboard.get("coverage", 100)
    if coverage < 80:
        return HookResult(
            success=False,
            block=True,
            message=f"❌ Coverage {coverage}% < 80%. Add tests before completing."
        )
    
    # Check for TODOs in modified files
    todos = blackboard.get("todos_in_code", [])
    if todos:
        return HookResult(
            success=False,
            block=True,
            message=f"❌ {len(todos)} TODOs found in code. Resolve or create issues before completing."
        )
    
    print("✅ Quality gate passed!")
    return HookResult(success=True)


# =============================================================================
# Example 4: Prompt Injection
# =============================================================================

# Register prompts that get injected at specific events
def setup_prompt_injections():
    """Setup context injection prompts."""
    
    # Inject at session start
    hook_system.register_prompt(
        HookEvent.SESSION_START,
        "Remember to check MEMORY.md and recent git commits for project context."
    )
    
    # Inject when user submits prompt
    hook_system.register_prompt(
        HookEvent.USER_PROMPT_SUBMIT,
        "If the request involves code changes, first check existing patterns in the codebase."
    )


# =============================================================================
# Example 5: Subagent Tracking
# =============================================================================

@hook_system.register(HookEvent.SUBAGENT_START)
async def track_subagent_start(context: HookContext) -> HookResult:
    """Track when subagents are spawned."""
    agent_id = context.metadata.get("agent_id", "unknown")
    agent_type = context.metadata.get("agent_type", "generic")
    
    print(f"🚀 Subagent started: {agent_type} ({agent_id})")
    
    # Track active agents in blackboard
    active = context.blackboard.get("active_subagents", [])
    active.append({
        "id": agent_id,
        "type": agent_type,
        "started": "now"
    })
    context.blackboard["active_subagents"] = active
    
    return HookResult(
        success=True,
        modified_context=context
    )


@hook_system.register(HookEvent.SUBAGENT_STOP)
async def track_subagent_stop(context: HookContext) -> HookResult:
    """Track when subagents complete."""
    agent_id = context.metadata.get("agent_id", "unknown")
    outcome = context.metadata.get("outcome", "unknown")
    
    print(f"✅ Subagent completed: {agent_id} ({outcome})")
    
    return HookResult(success=True)


# =============================================================================
# Example 6: Notification Handler
# =============================================================================

@hook_system.register(HookEvent.NOTIFICATION)
async def desktop_notification(context: HookContext) -> HookResult:
    """
    Send desktop notifications for important events.
    """
    message = context.metadata.get("message", "")
    notification_type = context.metadata.get("type", "info")
    
    # macOS notification
    try:
        import subprocess
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "EvoLoop"'
        ], check=True, capture_output=True)
    except Exception:
        pass  # Ignore if not on macOS or osascript fails
    
    return HookResult(success=True)


# =============================================================================
# Example 7: Error Recovery
# =============================================================================

@hook_system.register(HookEvent.ERROR)
async def error_recovery(context: HookContext) -> HookResult:
    """
    Attempt to recover from errors or at least log them properly.
    """
    error = context.error
    error_msg = str(error) if error else "Unknown error"
    
    # Log to console
    print(f"[ErrorHook] Captured error: {error_msg}")
    
    # Could send to error tracking service
    # Could attempt recovery based on error type
    # Could notify user
    
    return HookResult(
        success=True,
        data={"logged": True, "error": error_msg}
    )


# =============================================================================
# Example 8: Task Lifecycle Tracking
# =============================================================================

@hook_system.register(HookEvent.TASK_CREATED)
async def on_task_created(context: HookContext) -> HookResult:
    """Track new tasks."""
    task_id = context.metadata.get("task_id")
    task_name = context.metadata.get("task_name")
    
    print(f"📋 Task created: {task_name} ({task_id})")
    
    # Could integrate with project management tools
    # Could send to task tracking system
    
    return HookResult(success=True)


@hook_system.register(HookEvent.TASK_COMPLETED)
async def on_task_completed(context: HookContext) -> HookResult:
    """Track task completion."""
    task_id = context.metadata.get("task_id")
    task_name = context.metadata.get("task_name")
    status = context.metadata.get("status", "completed")
    
    print(f"✅ Task completed: {task_name} ({task_id}) - {status}")
    
    # Could archive task
    # Could update project metrics
    # Could trigger follow-up actions
    
    return HookResult(success=True)


# =============================================================================
# Example 9: Complex Matcher Pattern
# =============================================================================

@hook_system.register(
    HookEvent.POST_TOOL_USE,
    matcher="^ReadFile$|^Read$"
)
async def cache_file_reads(context: HookContext) -> HookResult:
    """
    Cache file read operations to avoid repeated reads.
    """
    file_path = context.tool_input.get("path") or context.tool_input.get("file_path")
    content = context.tool_result
    
    if file_path and content:
        # Store in blackboard cache
        cache = context.blackboard.get("file_cache", {})
        cache[file_path] = {
            "content": content,
            "timestamp": "now"
        }
        context.blackboard["file_cache"] = cache
        
        return HookResult(
            success=True,
            modified_context=context
        )
    
    return HookResult(success=True)


# =============================================================================
# Example 10: User Prompt Shortcuts
# =============================================================================

@hook_system.register(HookEvent.USER_PROMPT_SUBMIT)
async def command_shortcuts(context: HookContext) -> HookResult:
    """
    Expand command shortcuts before processing.
    
    Similar to Claude Code's slash commands.
    """
    prompt = context.metadata.get("prompt", "")
    
    shortcuts = {
        "/remember": "Please analyze our conversation and extract any important information worth remembering. Save relevant patterns, decisions, and context.",
        "/summary": "Please provide a concise summary of what we've accomplished in this session, including key decisions and outcomes.",
        "/status": "What's the current state of the task? What have we completed and what's remaining?",
        "/compact": "The context is getting long. Please summarize the key points and decisions so far, then continue with the current task.",
        "/fix": "Review the recent code changes for any issues, bugs, or improvements needed.",
        "/test": "Run the test suite and report results. If tests fail, help fix them.",
    }
    
    if prompt in shortcuts:
        modified_context = context
        modified_context.metadata["prompt"] = shortcuts[prompt]
        modified_context.metadata["original_prompt"] = prompt
        
        return HookResult(
            success=True,
            message=f"Expanded shortcut: {prompt}",
            modified_context=modified_context
        )
    
    return HookResult(success=True)


# =============================================================================
# Setup function to register all example hooks
# =============================================================================

def setup_example_hooks():
    """Register all example hooks."""
    setup_prompt_injections()
    print("✅ Example hooks registered!")
    print("\nRegistered handlers:")
    
    from app.core.engine.hooks import HookEvent
    
    for event in HookEvent:
        handlers = hook_system.get_handlers(event)
        if handlers:
            print(f"  {event.name}: {len(handlers)} handlers")


# Run setup if this file is executed
if __name__ == "__main__":
    setup_example_hooks()
