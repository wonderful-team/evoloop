import asyncio
import functools
from typing import TypeVar, Callable, Any

T = TypeVar("T")

async def run_in_thread(func: Callable[..., T], *args, **kwargs) -> T:
    """
    Run a blocking function in a separate thread to avoid blocking the event loop.
    Wraps loop.run_in_executor.
    """
    loop = asyncio.get_running_loop()
    partial_func = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, partial_func)
