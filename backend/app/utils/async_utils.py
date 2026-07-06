import asyncio
import functools
import logging
import weakref
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")

_ALL_LOOP_BOUND_RESOURCES: list[weakref.ReferenceType['LoopBoundResource']] = []


def run_in_thread_sync(func: Callable[..., T], *args, **kwargs) -> T:
    """Run a blocking function in a separate thread."""
    pass # Defined below


async def run_in_thread(func: Callable[..., T], *args, **kwargs) -> T:
    """
    Run a blocking function in a separate thread to avoid blocking the event loop.
    Wraps loop.run_in_executor.
    """
    loop = asyncio.get_running_loop()
    partial_func = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, partial_func)


class LoopBoundResource(Generic[R]):
    """
    Manages an async resource (like an HTTP client, Lock, or Queue) that is bound to a specific asyncio event loop.
    Ensures that Celery tasks (which create new event loops) get their own isolated resources, preventing "Event loop is closed" errors.
    """
    def __init__(self, factory: Callable[[], R], cleanup: Callable[[R], Awaitable[None]] | None = None, skip_flush: bool = False):
        self._factory = factory
        self._cleanup = cleanup
        self._skip_flush = skip_flush
        # WeakKeyDictionary ensures that when an event loop is garbage collected, the entry is automatically removed.
        self._resources: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, R] = weakref.WeakKeyDictionary()
        if not skip_flush:
            _ALL_LOOP_BOUND_RESOURCES.append(weakref.ref(self))

    def get(self) -> R:
        """Get or create the resource for the current event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # If no running loop, just return a new instance (usually for synchronous testing or setup)
            return self._factory()

        if loop not in self._resources:
            self._resources[loop] = self._factory()

        return self._resources[loop]

    async def flush(self) -> None:
        """
        Clean up the resource for the current event loop.
        Should be called at the end of a Celery task or when the resource is no longer needed.
        """
        try:
            loop = asyncio.get_running_loop()
            if loop in self._resources:
                resource = self._resources.pop(loop)
                if self._cleanup:
                    try:
                        await self._cleanup(resource)
                    except (TypeError, ValueError, RuntimeError, OSError) as e:
                        logger.warning(f"Error cleaning up loop-bound resource: {e}")
        except RuntimeError:
            pass

    async def flush_all(self) -> None:
        """Clean up all resources across all tracked loops (e.g., for global application shutdown)."""
        if self._cleanup:
            # Iterate over a list to avoid dictionary changed size during iteration
            for loop, resource in list(self._resources.items()):
                try:
                    await self._cleanup(resource)
                except (TypeError, ValueError, RuntimeError, OSError) as e:
                    logger.warning(f"Error cleaning up loop-bound resource during flush_all: {e}")
        self._resources.clear()


async def flush_loop_bound_resources() -> None:
    """
    Call this at the end of an isolated async task (like a Celery worker task)
    to cleanly flush all async resources associated with the current event loop.
    """
    for res_ref in _ALL_LOOP_BOUND_RESOURCES:
        res = res_ref()
        if res is not None:
            await res.flush()


# ============================================================================
# Parallel Execution Utilities
# ============================================================================


async def run_in_parallel(
    *coros: Awaitable[T],
    return_exceptions: bool = True
) -> list[T | Exception]:
    """
    Run multiple coroutines in parallel using asyncio.gather.
    
    Args:
        *coros: Coroutines to run
        return_exceptions: If True, exceptions are returned instead of raised
    
    Returns:
        List of results (or exceptions if return_exceptions=True)
    
    Example:
        results = await run_in_parallel(
            fetch_user(1),
            fetch_user(2),
            fetch_user(3)
        )
    """
    return await asyncio.gather(*coros, return_exceptions=return_exceptions)


async def run_with_timeout(
    coro: Awaitable[T],
    timeout: float,
    default: T | None = None
) -> T | None:
    """
    Run a coroutine with a timeout.
    
    Args:
        coro: Coroutine to run
        timeout: Timeout in seconds
        default: Default value to return on timeout
    
    Returns:
        Result of coroutine or default value
    
    Example:
        result = await run_with_timeout(
            fetch_data(),
            timeout=5.0,
            default={"error": "timeout"}
        )
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return default


def fire_and_forget(coro: Awaitable[T]) -> None:
    """
    Fire a coroutine and forget about it (don't await).
    Useful for background tasks.
    
    Args:
        coro: Coroutine to run in background
    
    Example:
        fire_and_forget(send_email(user.email))
    """
    asyncio.create_task(coro)


async def throttle(
    tasks: list[Awaitable[T]],
    max_concurrent: int = 5
) -> list[T]:
    """
    Run tasks with limited concurrency.
    
    Args:
        tasks: List of coroutines to run
        max_concurrent: Maximum number of concurrent tasks
    
    Returns:
        List of results in original order
    
    Example:
        results = await throttle(
            [fetch_url(url) for url in urls],
            max_concurrent=3
        )
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def _run_with_semaphore(task: Awaitable[T]) -> T:
        async with semaphore:
            return await task
    
    return await asyncio.gather(*[_run_with_semaphore(t) for t in tasks])


class TaskGroup:
    """
    Manages a group of tasks with easy add/run pattern.
    
    Example:
        group = TaskGroup()
        group.add(fetch_user(1))
        group.add(fetch_user(2))
        results = await group.run()
    """
    
    def __init__(self, return_exceptions: bool = True):
        self.tasks: list[Awaitable[T]] = []
        self.return_exceptions = return_exceptions
    
    def add(self, coro: Awaitable[T]) -> None:
        """Add a coroutine to the group."""
        self.tasks.append(coro)
    
    async def run(self) -> list[T | Exception]:
        """Run all tasks and return results."""
        if not self.tasks:
            return []
        results = await asyncio.gather(*self.tasks, return_exceptions=self.return_exceptions)
        self.tasks = []  # Clear after running
        return results
    
    def clear(self) -> None:
        """Clear all pending tasks."""
        self.tasks.clear()


# ============================================================================
# Synchronization Utilities
# ============================================================================


class AsyncEvent:
    """
    Async event with timeout support.
    
    Example:
        event = AsyncEvent()
        # In one task:
        await event.wait(timeout=5.0)
        # In another task:
        event.set()
    """
    
    def __init__(self):
        self._event = asyncio.Event()
    
    async def wait(self, timeout: float | None = None) -> bool:
        """
        Wait for event to be set.
        
        Args:
            timeout: Optional timeout in seconds
        
        Returns:
            True if event was set, False if timeout
        """
        if timeout is None:
            await self._event.wait()
            return True
        
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    def set(self) -> None:
        """Set the event."""
        self._event.set()
    
    def clear(self) -> None:
        """Clear the event."""
        self._event.clear()
    
    def is_set(self) -> bool:
        """Check if event is set."""
        return self._event.is_set()


# ============================================================================
# Debounce / Throttle
# ============================================================================


class Debouncer:
    """
    Debounce calls to a function.
    Only the last call within the delay period will be executed.
    
    Example:
        debouncer = Debouncer(save_to_db, delay=1.0)
        debouncer.trigger(data)  # Will call save_to_db after 1 second
        debouncer.trigger(data2)  # Resets timer, will only call with data2
    """
    
    def __init__(self, func: Callable[..., Awaitable[T]], delay: float):
        self.func = func
        self.delay = delay
        self._task: asyncio.Task | None = None
    
    def trigger(self, *args, **kwargs) -> None:
        """Trigger a debounced call."""
        if self._task is not None:
            self._task.cancel()
        
        async def _delayed():
            await asyncio.sleep(self.delay)
            await self.func(*args, **kwargs)
        
        self._task = asyncio.create_task(_delayed())
    
    def cancel(self) -> None:
        """Cancel pending call."""
        if self._task is not None:
            self._task.cancel()
            self._task = None


class Throttler:
    """
    Throttle calls to a function.
    Ensures the function is not called more often than the specified rate.
    
    Example:
        throttler = Throttler(update_ui, min_interval=0.5)
        throttler.trigger(data)  # Executes immediately
        throttler.trigger(data2)  # Queued, executes after 0.5s
    """
    
    def __init__(self, func: Callable[..., Awaitable[T]], min_interval: float):
        self.func = func
        self.min_interval = min_interval
        self._last_call: float = 0
        self._task: asyncio.Task | None = None
        self._pending_args: tuple | None = None
    
    def trigger(self, *args, **kwargs) -> None:
        """Trigger a throttled call."""
        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_call
        
        if elapsed >= self.min_interval:
            # Execute immediately
            self._execute(*args, **kwargs)
        else:
            # Queue for later
            self._pending_args = (args, kwargs)
            if self._task is None:
                delay = self.min_interval - elapsed
                self._task = asyncio.create_task(self._delayed_execute(delay))
    
    def _execute(self, *args, **kwargs) -> None:
        """Execute the function."""
        self._last_call = asyncio.get_running_loop().time()
        asyncio.create_task(self.func(*args, **kwargs))
    
    async def _delayed_execute(self, delay: float) -> None:
        """Execute after delay."""
        await asyncio.sleep(delay)
        if self._pending_args is not None:
            args, kwargs = self._pending_args
            self._execute(*args, **kwargs)
            self._pending_args = None
        self._task = None

