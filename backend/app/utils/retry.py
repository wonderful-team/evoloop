"""
Retry Utilities Module.

Provides generic retry decorators and specific service health check helpers.
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy import Engine
from sqlmodel import Session, select
from tenacity import (
    after_log,
    before_log,
    retry,
    stop_after_attempt,
    wait_fixed,
)

# Generic Type for callable
T = TypeVar("T", bound=Callable[..., Any])

logger = logging.getLogger(__name__)

# Standard constants
DEFAULT_MAX_TRIES = 60 * 5  # 5 minutes
DEFAULT_WAIT_SECONDS = 1


def get_retry_decorator(
    max_tries: int = DEFAULT_MAX_TRIES,
    wait_seconds: float = DEFAULT_WAIT_SECONDS,
    logger_instance: logging.Logger = logger,
    log_level: int = logging.INFO,
) -> Callable[[T], T]:
    """
    Get a configured tenacity retry decorator.

    Args:
        max_tries: Maximum number of attempts
        wait_seconds: Wait time between attempts
        logger_instance: Logger to use for retry logs
        log_level: Logging level for retry attempts

    Returns:
        Decorated function
    """
    return retry(
        stop=stop_after_attempt(max_tries),
        wait=wait_fixed(wait_seconds),
        before=before_log(logger_instance, log_level),
        after=after_log(logger_instance, logging.WARN),
    )


def wait_for_db(db_engine: Engine) -> None:
    """
    Wait for database to be ready.
    Retries automatically for a configurable period (default 5 mins).
    """

    @get_retry_decorator()
    def _check_db() -> None:
        try:
            with Session(db_engine) as session:
                # Try to create session to check if DB is awake
                session.exec(select(1))
        except Exception as e:
            logger.error(f"Database not ready yet: {e}")
            raise e

    logger.info("Waiting for database connection...")
    _check_db()
    logger.info("Database connection established.")


# ============================================================================
# Async Retry Decorators
# ============================================================================


import asyncio
import functools
from typing import TypeVar

T = TypeVar("T")


def retry_async(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
):
    """
    Decorator to retry an async function on failure.

    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between attempts (seconds)
        backoff: Multiplier for delay after each attempt
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback function(exc, attempt_number)

    Example:
        @retry_async(max_attempts=3, delay=1.0)
        async def fetch_data():
            return await api.get_data()
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        raise

                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {current_delay}s..."
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

            # Should never reach here
            raise RuntimeError("Unexpected end of retry loop")

        return wrapper

    return decorator


def retry_with_fallback(fallback_value: T):
    """
    Decorator that returns a fallback value on failure instead of raising.

    Args:
        fallback_value: Value to return on failure

    Example:
        @retry_with_fallback(fallback_value={"error": "failed"})
        async def fetch_optional_data():
            return await api.get_data()
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"{func.__name__} failed, returning fallback: {e}")
                return fallback_value

        return wrapper

    return decorator


class RetryContext:
    """
    Context manager for retrying a block of code.

    Example:
        with RetryContext(max_attempts=3, delay=1.0) as retry:
            while retry.attempt():
                try:
                    result = await api.call()
                    retry.success()
                    break
                except Exception as e:
                    retry.fail(e)
    """

    def __init__(
        self,
        max_attempts: int = 3,
        delay: float = 1.0,
        backoff: float = 2.0,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff = backoff
        self.exceptions = exceptions
        self._attempt = 0
        self._current_delay = delay
        self._last_exception: Exception | None = None

    def attempt(self) -> bool:
        """Check if we should attempt again."""
        return self._attempt < self.max_attempts

    def success(self) -> None:
        """Mark current attempt as successful."""
        self._last_exception = None

    def fail(self, exception: Exception) -> None:
        """Mark current attempt as failed, will retry after delay."""
        self._last_exception = exception
        self._attempt += 1

        if self._attempt >= self.max_attempts:
            raise exception

        logger.warning(
            f"Attempt {self._attempt}/{self.max_attempts} failed: {exception}. "
            f"Retrying in {self._current_delay}s..."
        )

        # Sleep before next attempt
        import time

        time.sleep(self._current_delay)
        self._current_delay *= self.backoff

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val and self._last_exception is None:
            # Unhandled exception
            raise


# ============================================================================
# Simple Retry Function
# ============================================================================


async def retry_operation(
    operation: Callable[[], T],
    max_attempts: int = 3,
    delay: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """
    Retry an operation with simple interface.

    Args:
        operation: Callable that performs the operation
        max_attempts: Maximum number of attempts
        delay: Delay between attempts
        exceptions: Exceptions to catch

    Returns:
        Result of operation

    Raises:
        Last exception if all attempts fail
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except exceptions as e:
            if attempt == max_attempts:
                raise
            logger.warning(f"Attempt {attempt} failed: {e}. Retrying...")
            await asyncio.sleep(delay)

    raise RuntimeError("Unexpected end of retry loop")
