"""
Shared utilities for environment controllers.

This module provides common utilities used across MobileController,
DesktopController, and BrowserController without forcing an inheritance
hierarchy. Uses composition over inheritance for better flexibility.
"""
import asyncio
import logging
import time
from typing import Any, Callable

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils import (
    cleanup_file,
    normalize_coordinates,
    normalize_text,
    render_template,
)
from app.utils.text import truncate_output

logger = logging.getLogger(__name__)


class BatchStepResult(DynamicBaseModel):
    step: int
    action: str
    status: str
    result: Any = None
    latency_ms: int


class RecordingContext:
    """
    Unified recording context for action tracing across platforms.

    Encapsulates the common logic for recording actions with optional screenshots.
    Platform-specific details (screenshot method, context building) are injected
    via callable parameters.
    """

    def __init__(
        self,
        platform: str,
        recorder: Any | None,
        screenshot_actions: tuple[str, ...] = ("click", "tap", "type_text", "input_text"),
        disable_screenshot: bool = False
    ):
        self.platform = platform
        self.recorder = recorder
        self.screenshot_actions = screenshot_actions
        self.disable_screenshot = disable_screenshot

    async def record(
        self,
        action_type: str,
        params: dict,
        screenshot_fn: Callable[[], Any] | None = None,
        context_fn: Callable[[], dict] | None = None
    ) -> None:
        """
        Record an action with optional screenshot.

        Args:
            action_type: Type of action being recorded
            params: Action parameters
            screenshot_fn: Optional callable to capture screenshot
            context_fn: Optional callable to build context dict
        """
        if not self.recorder or not self.recorder.is_recording:
            return

        # Capture screenshot if needed
        shot = None
        should_capture = (
            not self.disable_screenshot
            and screenshot_fn is not None
            and action_type in self.screenshot_actions
        )

        if should_capture:
            try:
                shot = await screenshot_fn() if asyncio.iscoroutinefunction(screenshot_fn) else screenshot_fn()
            except Exception:
                pass  # Screenshot is optional

        # Build context
        context = await context_fn() if context_fn else {}

        # Record the action
        await self.recorder.record_action(
            action_type=action_type,
            platform=self.platform,
            parameters=params,
            context=context,
            screenshot_data=shot
        )


def resolve_element_alias(target: str | None, element_name: str | None) -> str | None:
    """
    Resolve parameter alias: prefer element_name, fall back to target.

    Many actions accept both 'target' and 'element_name' for backward compatibility.
    This function ensures consistent handling of the alias.
    """
    return element_name if element_name else target


async def run_with_timeout(
    coro,
    timeout: float,
    default: Any = None
):
    """Run a coroutine with timeout, return default on timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return default


class BatchExecutor:
    """Helper for executing batch actions with error handling."""

    def __init__(self, continue_on_error: bool = True, delay_ms: int = 0):
        self.continue_on_error = continue_on_error
        self.delay_ms = delay_ms
        self.results: list[BatchStepResult] = []

    async def execute(
        self,
        actions: list[dict],
        executor_func,
        total: int | None = None
    ) -> list[BatchStepResult]:
        """
        Execute a list of actions.

        Args:
            actions: List of action dicts
            executor_func: Async function to execute each action
            total: Optional total count (for progress)
        """
        total = total or len(actions)
        for i, action_dict in enumerate(actions, 1):
            step_start = time.time()
            step_action = action_dict.get("action", "unknown")

            try:
                result = await executor_func(action_dict)
                latency = int((time.time() - step_start) * 1000)
                self.results.append(BatchStepResult(
                    step=i,
                    action=step_action,
                    status="success" if not str(result).startswith("Error") else "error",
                    result=result,
                    latency_ms=latency
                ))
            except Exception as e:
                latency = int((time.time() - step_start) * 1000)
                self.results.append(BatchStepResult(
                    step=i,
                    action=step_action,
                    status="error",
                    result=str(e),
                    latency_ms=latency
                ))
                if not self.continue_on_error:
                    break

            if i < total and self.delay_ms > 0:
                await asyncio.sleep(self.delay_ms / 1000)

        return self.results

    def format_summary(self, elapsed_time: float) -> str:
        """Format batch execution summary using template."""
        total = len(self.results)
        ok = sum(1 for r in self.results if r["status"] == "success")
        fail = total - ok
        return render_template(
            "report/batch_summary.prompt.j2",
            results=self.results,
            total=total,
            ok=ok,
            fail=fail,
            elapsed_time=round(elapsed_time, 2)
        )


__all__ = [
    "BatchExecutor",
    "RecordingContext",
    "cleanup_file",
    "normalize_coordinates",
    "normalize_text",
    "render_template",
    "resolve_element_alias",
    "run_with_timeout",
    "truncate_output",
]
