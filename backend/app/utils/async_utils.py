import asyncio
import logging
import weakref
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

R = TypeVar("R")

_ALL_LOOP_BOUND_RESOURCES: list[weakref.ReferenceType["LoopBoundResource"]] = []


def is_in_event_loop() -> bool:
    """
    Return True when a running asyncio event loop exists (e.g. inside a server
    process or worker thread). Interactive stdin prompts must never block the
    event loop; callers that run in both sync CLI and async server contexts
    should guard with this.
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class LoopBoundResource(Generic[R]):
    """
    Manages an async resource (like an HTTP client, Lock, or Queue) that is bound to a specific asyncio event loop.
    Ensures that Celery tasks (which create new event loops) get their own isolated resources, preventing "Event loop is closed" errors.
    """

    def __init__(
        self,
        factory: Callable[[], R],
        cleanup: Callable[[R], Awaitable[None]] | None = None,
        skip_flush: bool = False,
    ):
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
                        logger.warning(
                            "Error cleaning up loop-bound resource: %s", e, exc_info=True
                        )
        except RuntimeError:
            pass

    async def flush_all(self) -> None:
        """Clean up all resources across all tracked loops (e.g., for global application shutdown)."""
        if self._cleanup:
            # Iterate over a list to avoid dictionary changed size during iteration
            for _loop, resource in list(self._resources.items()):
                try:
                    await self._cleanup(resource)
                except (TypeError, ValueError, RuntimeError, OSError) as e:
                    logger.warning(
                        "Error cleaning up loop-bound resource during flush_all: %s",
                        e,
                        exc_info=True,
                    )
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



