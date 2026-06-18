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
        await formatter.format(context.tool_input.path if context.tool_input else None)

    # Trigger hooks
    await hook_system.trigger(HookEvent.PRE_COMPACT, context)
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import Enum, auto
from typing import Any, overload

from app.core.engine.hooks.schemas import HookContext, HookResult

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

    @overload
    def register(
        self,
        event: HookEvent,
        handler: None = None,
        priority: int = 100,
        matcher: str | None = None,
    ) -> Callable[[HookHandler], HookHandler]: ...

    @overload
    def register(
        self,
        event: HookEvent,
        handler: HookHandler,
        priority: int = 100,
        matcher: str | None = None,
    ) -> HookHandler: ...

    def register(
        self,
        event: HookEvent,
        handler: HookHandler | None = None,
        priority: int = 100,
        matcher: str | None = None,
    ) -> HookHandler | Callable[[HookHandler], HookHandler]:
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
            self._hooks[event].sort(key=lambda h: h._hook_priority)

            match_str = f" [matcher: {matcher}]" if matcher else ""
            logger.debug(f"[HookSystem] Registered {func.__name__} for {event.name}{match_str}")
            return func

        if handler is None:
            # Used as decorator
            return decorator
        else:
            # Used as function
            return decorator(handler)

    def register_prompt(self, event: HookEvent, prompt: str) -> None:
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
            matcher = handler._hook_matcher
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
                    logger.warning(f"[HookSystem] {event.name} blocked by {handler.__name__}: {result.message}")
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
        # logger.debug(f"[HookSystem] {event.name} triggered {len(matching_handlers)} handlers in {elapsed:.3f}s")
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
            result = HookResult(success=True, data=result if result else {})  # type: ignore[arg-type]

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
            return [h for h in handlers if h._hook_matcher == matcher]
        return handlers.copy()

    def get_metrics(self, event: HookEvent | None = None) -> dict[HookEvent, dict[str, Any]]:
        """Get metrics for events."""
        if event:
            return {event: self._metrics.get(event, {})}
        return self._metrics.copy()


# Global hook system instance
hook_system = HookSystem()


# =============================================================================
# Setup Default Hooks
# =============================================================================

def setup_default_hooks():
    """Register default hook handlers."""
    # Import handlers lazily to avoid circular imports during module load
    from app.core.engine.hooks.handlers import (
        error_handler,
        notification_handler,
        post_tool_use_failure_logging,
        post_tool_use_logging,
        pre_compact_save_state,
        subagent_start_handler,
        subagent_stop_handler,
        user_prompt_submit_handler,
    )

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

    # Error handling
    hook_system.register(HookEvent.ERROR, error_handler, priority=10)

    # Quality gates (disabled by default, enable if needed)
    # hook_system.register(HookEvent.STOP, stop_quality_gate, priority=50)

    # Prompt injections (examples)
    # hook_system.register_prompt(HookEvent.SESSION_START, "Remember to check MEMORY.md")

    logger.info("[HookSystem] Default hooks registered")


# Setup on module load
setup_default_hooks()
