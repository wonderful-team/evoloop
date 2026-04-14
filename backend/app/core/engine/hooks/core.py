"""
EvoLoop Hooks System - Lifecycle event management inspired by Claude Code.

This module provides a hook system for capturing lifecycle events:
- SessionStart: Session initialization
- UserPromptSubmit: User input validation
- PreToolUse: Tool execution validation (can block)
- PostToolUse: Tool result processing
- PostToolUseFailure: Tool failure handling
- PreCompact: CRITICAL - Save state before context compression
- PostCompact: After compression cleanup
- Stop: Response completion (quality gates)
- Notification: User notification
- SessionEnd: Session cleanup and persistence

Usage:
    from app.core.engine.hooks import hook_system, HookEvent
    
    # Register a handler
    @hook_system.register(HookEvent.PRE_COMPACT)
    async def save_state_before_compact(context):
        # Save critical state
        await memory_manager.save_checkpoint(context)
    
    # Register with matcher (filter by tool name)
    @hook_system.register(HookEvent.PostToolUse, matcher="^Write$|^Edit$")
    async def format_on_write(context):
        # Only triggers for Write/Edit tools
        await formatter.format(getattr(context.tool_input, "path", None) if context.tool_input else None)
    
    # Trigger hooks
    await hook_system.trigger(HookEvent.PRE_COMPACT, context)
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import Enum, auto
from typing import Any

from langchain_core.messages import BaseMessage
from pydantic import ConfigDict, Field

from app.core.engine.state.blackboard import BlackboardState
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class HookEvent(Enum):
    """Lifecycle events for hook system - matching Claude Code's architecture."""
    # Session lifecycle
    SESSION_START = auto()       # Session begins
    SESSION_END = auto()         # Session terminates

    # User interaction
    USER_PROMPT_SUBMIT = auto()  # User sends prompt
    NOTIFICATION = auto()        # System notification

    # Tool execution
    PRE_TOOL_USE = auto()        # Before tool executes (can block)
    POST_TOOL_USE = auto()       # After tool succeeds
    POST_TOOL_USE_FAILURE = auto()  # After tool fails

    # Permission
    PERMISSION_REQUEST = auto()  # Permission dialog shown
    PERMISSION_DENIED = auto()   # Tool call denied

    # Context management
    PRE_COMPACT = auto()         # Before context compression (CRITICAL)
    POST_COMPACT = auto()        # After context compression

    # Task/Agent lifecycle
    STOP = auto()                # Agent finishes response (quality gates)
    SUBAGENT_START = auto()      # Subagent spawned
    SUBAGENT_STOP = auto()       # Subagent completes
    TASK_CREATED = auto()        # Task created
    TASK_COMPLETED = auto()      # Task marked complete

    # Error handling
    ERROR = auto()               # Error occurred

    # Prompt Enrichment
    PROMPT_POLISHING = auto()    # Context-aware prompt polishing (domain expert hook)


class HookMetadata(DynamicBaseModel):
    """Dynamic metadata for hook events."""


class ToolInput(DynamicBaseModel):
    """Typed wrapper for tool input arguments."""


class HookExtra(DynamicBaseModel):
    """Arbitrary extra data attached to a hook context."""


class HookResultData(DynamicBaseModel):
    """Dynamic data payload returned by a hook handler."""


class HookContext(DynamicBaseModel):
    """Context passed to hook handlers - enriched with Claude Code-like fields."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: str
    project_id: int | None = None
    user_id: str | None = None
    messages: list[BaseMessage] = Field(default_factory=list)
    blackboard: BlackboardState | None = None
    metadata: HookMetadata = Field(default_factory=HookMetadata)

    # For tool-related events
    tool_name: str | None = None
    tool_input: ToolInput | None = None
    tool_result: Any | None = None
    tool_use_id: str | None = None
    error: Exception | None = None
    error_message: str | None = None

    # For permission events
    permission_mode: str | None = None  # "ask", "allow", "deny"

    # For compact events
    compact_trigger: str | None = None  # "manual" or "auto"

    # For dependency injection (optional, falls back to global singleton)
    memory_manager: Any | None = None  # MemoryManager instance
    memory_config: Any | None = None   # MemoryConfig instance

    # Allow arbitrary additional data
    extra: HookExtra = Field(default_factory=HookExtra)


class HookResult(DynamicBaseModel):
    """Result from hook handler."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool = True
    block: bool = False  # For blocking hooks (PreToolUse, Stop)
    retry: bool = False  # For PermissionDenied - allow retry
    message: str | None = None
    modified_context: HookContext | None = None
    data: HookResultData = Field(default_factory=HookResultData)
    error: Exception | None = None


# Handler type alias
HookHandler = Callable[[HookContext], HookResult | Awaitable[HookResult]]


class HookSystem:
    """
    Central hook system for EvoLoop lifecycle events.
    
    Enhanced with Claude Code features:
    - Matcher filtering (regex patterns)
    - Priority ordering
    - Blocking capability
    - Multiple handler types (function, prompt)
    """

    def __init__(self):
        self._hooks: dict[HookEvent, list[HookHandler]] = {
            event: [] for event in HookEvent
        }
        self._prompts: dict[HookEvent, list[str]] = {
            event: [] for event in HookEvent
        }
        self._metrics: dict[HookEvent, dict[str, Any]] = {}
        logger.info("[HookSystem] Initialized")

    def register(
        self,
        event: HookEvent,
        handler: HookHandler | None = None,
        priority: int = 100,
        matcher: str | None = None,
    ) -> Callable | HookHandler:
        """
        Register a hook handler with optional matcher pattern.
        
        Can be used as decorator:
            @hook_system.register(HookEvent.PRE_COMPACT)
            async def my_handler(context):
                ...
        
        With matcher (only triggers for matching tool names):
            @hook_system.register(HookEvent.PostToolUse, matcher="^Write$|^Edit$")
            async def format_code(context):
                ...
        
        Args:
            event: The event to listen for
            handler: The handler function (if not used as decorator)
            priority: Lower number = higher priority (default 100)
            matcher: Regex pattern to filter by tool_name (optional)
        """
        def decorator(func: HookHandler) -> HookHandler:
            # Store metadata in function attributes
            func._hook_priority = priority
            func._hook_event = event
            func._hook_matcher = matcher
            func._hook_name = func.__name__

            self._hooks[event].append(func)
            # Sort by priority
            self._hooks[event].sort(key=lambda h: getattr(h, '_hook_priority', 100))

            match_str = f" [matcher: {matcher}]" if matcher else ""
            logger.debug(f"[HookSystem] Registered {func.__name__} for {event.name}{match_str}")
            return func

        if handler is None:
            # Used as decorator
            return decorator
        else:
            # Used as function
            return decorator(handler)

    def register_prompt(
        self,
        event: HookEvent,
        prompt: str,
    ) -> None:
        """
        Register a prompt to be injected at the event.
        
        This is a lightweight alternative to function handlers for
        simple context injection.
        
        Args:
            event: The event to attach to
            prompt: The prompt text to inject
        """
        if event not in self._prompts:
            self._prompts[event] = []
        self._prompts[event].append(prompt)
        logger.debug(f"[HookSystem] Registered prompt for {event.name}")

    def unregister(self, event: HookEvent, handler: HookHandler) -> bool:
        """Unregister a handler."""
        if handler in self._hooks[event]:
            self._hooks[event].remove(handler)
            logger.debug(f"[HookSystem] Unregistered {handler.__name__} from {event.name}")
            return True
        return False

    async def trigger(
        self,
        event: HookEvent,
        context: HookContext,
        blocking: bool = False,
    ) -> HookResult:
        """
        Trigger all handlers for an event.
        
        Handlers with matchers are filtered based on context.tool_name.
        
        Args:
            event: Event to trigger
            context: Context to pass to handlers
            blocking: Whether handlers can block execution
        
        Returns:
            Combined result from all handlers
        """
        handlers = self._hooks.get(event, [])
        if not handlers:
            return HookResult(success=True)

        # Filter handlers by matcher
        matching_handlers = []
        for handler in handlers:
            matcher = getattr(handler, '_hook_matcher', None)
            if matcher:
                # Check if tool_name matches the pattern
                tool_name = context.tool_name or ""
                if not re.search(matcher, tool_name):
                    continue  # Skip non-matching handlers
            matching_handlers.append(handler)

        if not matching_handlers:
            return HookResult(success=True)

        start_time = datetime.utcnow()
        results = []

        for handler in matching_handlers:
            try:
                result = await self._execute_handler(handler, context)
                results.append(result)

                # If blocking and handler says block, stop immediately
                if blocking and result.block:
                    logger.warning(
                        f"[HookSystem] {event.name} blocked by {handler.__name__}: {result.message}"
                    )
                    return result

                # If PermissionDenied and retry requested
                if event == HookEvent.PERMISSION_DENIED and result.retry:
                    return result

                # Update context if modified
                if result.modified_context:
                    context = result.modified_context

            except Exception as e:
                logger.error(f"[HookSystem] Handler {handler.__name__} failed: {e}")
                if event == HookEvent.ERROR:
                    # Don't recurse on error
                    break
                results.append(HookResult(success=False, error=e))

        # Record metrics
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        self._metrics[event] = {
            "handlers_called": len(matching_handlers),
            "handlers_succeeded": sum(1 for r in results if r.success),
            "elapsed_seconds": elapsed,
        }

        # Combine results
        # Merge data from all handlers
        merged_data = {}
        for r in results:
            if r.data:
                merged_data.update(r.data)

        final_result = HookResult(
            success=all(r.success for r in results),
            block=any(r.block for r in results),
            retry=any(r.retry for r in results),
            message="; ".join(r.message for r in results if r.message),
            modified_context=context,
            data=merged_data,
        )

        logger.debug(f"[HookSystem] {event.name} triggered {len(matching_handlers)} handlers in {elapsed:.3f}s")
        return final_result

    def get_prompts(self, event: HookEvent) -> list[str]:
        """Get all registered prompts for an event."""
        return self._prompts.get(event, []).copy()

    async def _execute_handler(
        self,
        handler: HookHandler,
        context: HookContext,
    ) -> HookResult:
        """Execute a single handler."""
        result = handler(context)

        # Handle both sync and async handlers
        if asyncio.iscoroutine(result):
            result = await result

        # Ensure result is HookResult
        if not isinstance(result, HookResult):
            result = HookResult(success=True, data=result if result else {})

        return result

    def get_handlers(
        self,
        event: HookEvent,
        matcher: str | None = None,
    ) -> list[HookHandler]:
        """
        Get all handlers for an event.
        
        Args:
            event: The event
            matcher: Optional filter by matcher pattern
        """
        handlers = self._hooks.get(event, [])
        if matcher:
            return [h for h in handlers if getattr(h, '_hook_matcher', None) == matcher]
        return handlers.copy()

    def get_metrics(self, event: HookEvent | None = None) -> dict[str, Any]:
        """Get metrics for events."""
        if event:
            return self._metrics.get(event, {})
        return self._metrics.copy()


# Global hook system instance
hook_system = HookSystem()


# =============================================================================
# Pre-built Hook Handlers
# =============================================================================

async def session_start_handler(context: HookContext) -> HookResult:
    """
    Initialize session state when session starts.
    
    Loads hot memories and sets up initial context.
    """
    logger.info(f"[SessionStart] Initializing session {context.thread_id}")

    return HookResult(
        success=True,
        data={"initialized": True, "thread_id": context.thread_id}
    )


async def pre_compact_save_state(context: HookContext) -> HookResult:
    """
    CRITICAL: Save state before context compression.

    This is the most important hook - it prevents loss of critical
    information when the context window fills up.

    Saves:
    - Task progress
    - Key decisions made
    - Remaining work
    - Important context
    """
    start_time = datetime.utcnow()
    logger.info(f"[PreCompact] 🔄 Starting checkpoint save for thread={context.thread_id}")

    # Use provided memory_manager from context (injected via container)
    mm = context.memory_manager
    if mm is None:
        # Fallback to singleton container if not provided in context
        from app.core.memory.lifespan import MemoryLifespanManager
        if not MemoryLifespanManager.is_initialized():
            logger.debug("[PreCompact] Initializing MemoryLifespanManager...")
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        mm = container.memory_manager
        logger.debug("[PreCompact] Got memory_manager from singleton container")

    try:
        # Extract critical information from messages
        extract_start = datetime.utcnow()
        task_progress = _extract_task_progress(context.messages)
        key_decisions = _extract_decisions(context.messages)
        extract_elapsed = (datetime.utcnow() - extract_start).total_seconds()
        logger.debug(f"[PreCompact] Extracted task_progress ({len(task_progress)} chars) and {len(key_decisions)} decisions in {extract_elapsed:.3f}s")

        # Check for duplicate checkpoint (same thread_id + same task_progress in last 5 minutes)
        duplicate_check_start = datetime.utcnow()
        existing_checkpoints = await mm.list_memories(type_filter=MemoryType.PROJECT)

        # Look for recent checkpoint with same task progress
        recent_duplicate = None
        for cp_summary in existing_checkpoints:
            if cp_summary.id.startswith(f"checkpoint_{context.thread_id}"):
                # Load full entry to check content
                cp_entry = await mm.get_memory(cp_summary.id)
                if cp_entry:
                    try:
                        cp_data = yaml.safe_load(cp_entry.content)
                        if cp_data.get("task_progress") == task_progress:
                            # Check if within 5 minutes
                            cp_time = datetime.fromisoformat(cp_data.get("timestamp", "2000-01-01"))
                            if (datetime.utcnow() - cp_time).total_seconds() < 300:  # 5 minutes
                                recent_duplicate = cp_entry
                                logger.warning(f"[PreCompact] ⚠️ Found duplicate checkpoint from {cp_time.isoformat()}: {cp_entry.id}")
                                break
                    except Exception as e:
                        logger.debug(f"[PreCompact] Failed to parse existing checkpoint {cp_summary.id}: {e}")

        duplicate_check_elapsed = (datetime.utcnow() - duplicate_check_start).total_seconds()
        logger.debug(f"[PreCompact] Duplicate check: scanned {len(existing_checkpoints)} entries in {duplicate_check_elapsed:.3f}s")

        if recent_duplicate:
            logger.info(f"[PreCompact] ⏭️ Skipping duplicate checkpoint for thread={context.thread_id}")
            return HookResult(
                success=True,
                data={"checkpoint": None, "skipped": True, "reason": "duplicate_within_5min"},
            )

        # Create checkpoint data
        checkpoint = {
            "timestamp": datetime.utcnow().isoformat(),
            "thread_id": context.thread_id,
            "message_count": len(context.messages),
            "task_progress": task_progress,
            "key_decisions": key_decisions,
            "remaining_work": getattr(context.blackboard, "remaining_work", None) if context.blackboard else None,
            "current_goal": getattr(context.blackboard, "current_goal", None) if context.blackboard else None,
            "compact_trigger": context.compact_trigger or "auto",
        }
        logger.debug(f"[PreCompact] Checkpoint data: {len(context.messages)} messages, trigger={checkpoint['compact_trigger']}")

        # Save to memory
        save_start = datetime.utcnow()
        memory_entry = MemoryEntry(
            id=f"checkpoint_{context.thread_id}_{int(datetime.utcnow().timestamp())}",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.PRIVATE,
            title=f"Context Checkpoint - {checkpoint['task_progress'][:50]}...",
            description=f"Auto-saved before context compaction ({checkpoint['compact_trigger']})",
            content=yaml.safe_dump(checkpoint),
            user_id=context.user_id,
            project_id=context.project_id,
            tags=["checkpoint", "pre-compact"],
        )

        await mm.save_memory(memory_entry)
        save_elapsed = (datetime.utcnow() - save_start).total_seconds()

        total_elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"[PreCompact] ✅ Checkpoint saved: {memory_entry.id} in {total_elapsed:.3f}s (save: {save_elapsed:.3f}s)")

        # Create summary for context injection
        summary = f"""
[Context Compaction Checkpoint]
Task: {checkpoint['task_progress'][:100]}
Decisions: {len(checkpoint['key_decisions'])} key decisions made
Remaining: {checkpoint['remaining_work'] or 'Unknown'}
"""

        return HookResult(
            success=True,
            data={"checkpoint": checkpoint, "summary": summary, "checkpoint_id": memory_entry.id},
        )

    except Exception as e:
        total_elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"[PreCompact] ❌ Failed to save state after {total_elapsed:.3f}s: {e}", exc_info=True)
        return HookResult(success=False, error=e)


def _extract_task_progress(messages: list[BaseMessage]) -> str:
    """Extract current task progress from messages."""
    if not messages:
        return "No progress recorded"

    # Look for the most recent human message
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == 'human':
            return str(msg.content)[:200]

    return "Unknown task"


def _extract_decisions(messages: list[BaseMessage]) -> list[str]:
    """Extract key decisions from messages."""
    decisions = []

    for msg in messages:
        if hasattr(msg, 'type') and msg.type == 'ai':
            content = str(msg.content).lower()
            # Look for decision indicators
            if any(keyword in content for keyword in ['decided', 'decision', 'choose', 'selected', 'we will']):
                decisions.append(str(msg.content)[:150])

    return decisions[-5:]  # Last 5 decisions


async def session_end_auto_extract(context: HookContext) -> HookResult:
    """
    Auto-extract learnings when session ends.
    
    This replaces manual "remember" calls with automatic extraction.
    """
    from app.core.memory.auto_extraction import AutoMemoryExtractor

    try:
        # Use DI if memory_manager provided, otherwise use global singleton
        if context.memory_manager is not None and context.memory_config is not None:
            extractor = AutoMemoryExtractor(
                memory_manager=context.memory_manager,
                config=context.memory_config,
            )
        else:
            from app.core.memory.auto_extraction import auto_extractor
            extractor = auto_extractor

        if len(context.messages) >= 4:
            # Trigger auto-extraction
            extracted = await extractor.maybe_extract(
                thread_id=context.thread_id,
                messages=context.messages,
                project_id=context.project_id,
                user_id=context.user_id,
            )

            if extracted:
                logger.info(f"[SessionEnd] Auto-extracted {len(extracted)} memories")
                return HookResult(
                    success=True,
                    data={"extracted_count": len(extracted)},
                )

        return HookResult(success=True)

    except Exception as e:
        logger.error(f"[SessionEnd] Auto-extraction failed: {e}")
        return HookResult(success=False, error=e)


async def post_tool_use_logging(context: HookContext) -> HookResult:
    """Log tool usage for analytics and memory."""
    if not context.tool_name:
        return HookResult(success=True)

    logger.debug(f"[ToolUse] {context.tool_name}: success")

    # Track tool usage for quality scoring
    # Could track which tools lead to successful outcomes

    return HookResult(success=True)


async def post_tool_use_failure_logging(context: HookContext) -> HookResult:
    """Log tool failures for debugging and improvement."""
    if not context.tool_name:
        return HookResult(success=True)

    error_str = str(context.error) if context.error else context.error_message or "Unknown error"
    logger.warning(f"[ToolUseFailure] {context.tool_name} failed: {error_str}")

    return HookResult(
        success=True,
        data={
            "tool_name": context.tool_name,
            "error": error_str,
            "tool_input": context.tool_input,
        }
    )


async def stop_quality_gate(context: HookContext) -> HookResult:
    """
    Quality gate at Stop event - can block completion if checks fail.
    
    This is where you can enforce:
    - All tests must pass
    - Code must be formatted
    - No TODOs left in code
    """
    blackboard = context.blackboard

    # Check if there were any failures in the session
    if getattr(blackboard, "test_failures", None) if blackboard else None:
        return HookResult(
            success=False,
            block=True,
            message="Tests failed. Please fix before completing.",
        )

    if getattr(blackboard, "lint_errors", None) if blackboard else None:
        return HookResult(
            success=False,
            block=True,
            message="Lint errors found. Please fix formatting.",
        )

    logger.debug("[Stop] Quality gate passed")
    return HookResult(success=True)


async def notification_handler(context: HookContext) -> HookResult:
    """
    Handle system notifications.
    
    Can be used for:
    - Desktop notifications
    - Slack/Teams alerts
    - Email notifications
    - Sound alerts (TTS)
    """
    message = context.metadata.get("message", "")
    notification_type = context.metadata.get("type", "info")

    logger.info(f"[Notification] {notification_type}: {message}")

    # Example: Desktop notification (macOS)
    # import subprocess
    # subprocess.run([
    #     "osascript", "-e",
    #     f'display notification "{message}" with title "EvoLoop"'
    # ])

    return HookResult(
        success=True,
        data={"notified": True, "type": notification_type}
    )


async def subagent_start_handler(context: HookContext) -> HookResult:
    """
    Track when subagents are spawned.
    
    Useful for:
    - Monitoring parallel execution
    - Resource tracking
    - Debugging multi-agent workflows
    """
    agent_id = context.metadata.get("agent_id", "unknown")
    agent_type = context.metadata.get("agent_type", "generic")
    parent_task = context.metadata.get("parent_task", "")

    logger.info(f"[SubagentStart] Spawned {agent_type} agent ({agent_id}) for: {parent_task[:50]}...")

    # Track in blackboard
    active_agents = getattr(context.blackboard, "active_subagents", []) if context.blackboard else []
    active_agents.append({
        "agent_id": agent_id,
        "agent_type": agent_type,
        "started_at": datetime.utcnow().isoformat(),
    })
    if context.blackboard:
        context.blackboard.active_subagents = active_agents

    return HookResult(
        success=True,
        data={"agent_id": agent_id, "active_count": len(active_agents)},
        modified_context=context,
    )


async def subagent_stop_handler(context: HookContext) -> HookResult:
    """
    Track when subagents complete.
    
    Useful for:
    - Collecting results
    - Cleanup
    - Coordination with parent
    """
    agent_id = context.metadata.get("agent_id", "unknown")
    outcome = context.metadata.get("outcome", "unknown")

    logger.info(f"[SubagentStop] Agent {agent_id} completed with outcome: {outcome}")

    # Update tracking
    active_agents = getattr(context.blackboard, "active_subagents", []) if context.blackboard else []
    active_agents = [a for a in active_agents if a["agent_id"] != agent_id]
    if context.blackboard:
        context.blackboard.active_subagents = active_agents

    # Track completed
    completed = getattr(context.blackboard, "completed_subagents", []) if context.blackboard else []
    completed.append({
        "agent_id": agent_id,
        "outcome": outcome,
        "completed_at": datetime.utcnow().isoformat(),
    })
    if context.blackboard:
        context.blackboard.completed_subagents = completed

    return HookResult(
        success=True,
        data={"agent_id": agent_id, "remaining": len(active_agents)},
        modified_context=context,
    )


async def task_created_handler(context: HookContext) -> HookResult:
    """
    Track task creation.
    
    Useful for:
    - Task tracking
    - Audit logging
    - Project management integration
    """
    task_id = context.metadata.get("task_id", "")
    task_name = context.metadata.get("task_name", "")
    task_description = context.metadata.get("description", "")

    logger.info(f"[TaskCreated] Task '{task_name}' ({task_id}) created")

    return HookResult(
        success=True,
        data={"task_id": task_id, "tracked": True}
    )


async def task_completed_handler(context: HookContext) -> HookResult:
    """
    Track task completion.
    
    Useful for:
    - Task archival
    - Metrics collection
    - Follow-up actions
    """
    task_id = context.metadata.get("task_id", "")
    task_name = context.metadata.get("task_name", "")
    final_status = context.metadata.get("status", "completed")

    logger.info(f"[TaskCompleted] Task '{task_name}' ({task_id}) marked as {final_status}")

    return HookResult(
        success=True,
        data={"task_id": task_id, "archived": True, "status": final_status}
    )


async def user_prompt_submit_handler(context: HookContext) -> HookResult:
    """
    Process user prompt before it's handled.
    
    Useful for:
    - Prompt validation
    - Command shortcuts
    - Context injection
    """
    prompt = context.metadata.get("prompt", "")

    # Example: Command shortcuts
    shortcuts = {
        "/remember": "Please extract and save any important information from our conversation.",
        "/summary": "Please provide a summary of what we've accomplished so far.",
        "/compact": "The context is getting long. Please summarize key points and continue.",
    }

    if prompt in shortcuts:
        modified_context = context
        modified_context.metadata["prompt"] = shortcuts[prompt]
        return HookResult(
            success=True,
            message=f"Expanded shortcut: {prompt}",
            modified_context=modified_context,
        )

    return HookResult(success=True)


async def error_handler(context: HookContext) -> HookResult:
    """
    Global error handling.
    
    Can be used for:
    - Error logging
    - Recovery attempts
    - Alerting
    """
    error = context.error
    error_message = str(error) if error else context.error_message or "Unknown error"

    logger.error(f"[ErrorHook] {error_message}")

    # Could send to error tracking service
    # Could attempt recovery
    # Could notify user

    return HookResult(
        success=True,
        data={"logged": True, "error": error_message}
    )


# =============================================================================
# Setup Default Hooks
# =============================================================================

def setup_default_hooks():
    """Register default hook handlers."""
    # Session lifecycle
    hook_system.register(HookEvent.SESSION_START, session_start_handler, priority=10)
    hook_system.register(HookEvent.SESSION_END, session_end_auto_extract, priority=100)

    # User interaction
    hook_system.register(HookEvent.USER_PROMPT_SUBMIT, user_prompt_submit_handler, priority=50)
    hook_system.register(HookEvent.NOTIFICATION, notification_handler, priority=100)

    # Tool execution
    hook_system.register(HookEvent.POST_TOOL_USE, post_tool_use_logging, priority=200)
    hook_system.register(HookEvent.POST_TOOL_USE_FAILURE, post_tool_use_failure_logging, priority=100)

    # Context management
    hook_system.register(HookEvent.PRE_COMPACT, pre_compact_save_state, priority=10)

    # Agent/Subagent lifecycle
    hook_system.register(HookEvent.SUBAGENT_START, subagent_start_handler, priority=50)
    hook_system.register(HookEvent.SUBAGENT_STOP, subagent_stop_handler, priority=50)

    # Task lifecycle
    hook_system.register(HookEvent.TASK_CREATED, task_created_handler, priority=100)
    hook_system.register(HookEvent.TASK_COMPLETED, task_completed_handler, priority=100)

    # Error handling
    hook_system.register(HookEvent.ERROR, error_handler, priority=10)

    # Quality gates (disabled by default, enable if needed)
    # hook_system.register(HookEvent.STOP, stop_quality_gate, priority=50)

    # Prompt injections (examples)
    # hook_system.register_prompt(HookEvent.SESSION_START, "Remember to check MEMORY.md")

    logger.info("[HookSystem] Default hooks registered")


# Import at bottom to avoid circular imports
import yaml

from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

# Setup on module load
setup_default_hooks()
