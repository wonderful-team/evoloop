import asyncio
import functools
import logging
import weakref
from collections.abc import Callable, Awaitable
from typing import TypeVar, Generic

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
    def __init__(self, factory: Callable[[], R], cleanup: Callable[[R], Awaitable[None]] | None = None):
        self._factory = factory
        self._cleanup = cleanup
        # WeakKeyDictionary ensures that when an event loop is garbage collected, the entry is automatically removed.
        self._resources: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, R] = weakref.WeakKeyDictionary()
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
                    except Exception as e:
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
                except Exception as e:
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

