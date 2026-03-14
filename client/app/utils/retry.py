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
