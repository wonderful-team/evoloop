"""SQLAlchemy connection pool instrumentation.

Tracks checkout durations and warns about long-lived connections, which are the
most common root cause of "QueuePool limit ... reached" errors under load.
"""

import logging
import threading
import time
from typing import Any

from sqlalchemy import event

logger = logging.getLogger("db.pool")

_checkout_times: dict[int, float] = {}
_checkout_lock = threading.Lock()


def install(engine: Any, slow_threshold: float) -> None:
    """Install checkout/checkin listeners on *engine* (sync or async sync_engine)."""

    @event.listens_for(engine, "checkout")
    def _on_checkout(_dbapi_conn: Any, connection_record: Any, _connection_proxy: Any) -> None:  # noqa: ARG001
        with _checkout_lock:
            _checkout_times[id(connection_record)] = time.monotonic()

    @event.listens_for(engine, "checkin")
    def _on_checkin(_dbapi_conn: Any, connection_record: Any) -> None:  # noqa: ARG001
        now = time.monotonic()
        with _checkout_lock:
            start = _checkout_times.pop(id(connection_record), None)
        if start is None:
            return
        duration = now - start
        if duration > slow_threshold:
            logger.warning(
                "[DBPool] Slow connection checkout: %.2fs (record=%r). "
                "Long-lived sessions or uncommitted transactions are a common cause of pool exhaustion.",
                duration,
                connection_record,
            )


def pool_stats(engine: Any) -> dict[str, Any] | None:
    """Return current pool statistics for *engine*, or None if unavailable."""
    pool = getattr(engine, "pool", None)
    if pool is None:
        return None
    return {
        "size": getattr(pool, "size", lambda: -1)(),
        "checked_in": getattr(pool, "checkedin", lambda: -1)(),
        "checked_out": getattr(pool, "checkedout", lambda: -1)(),
        "overflow": getattr(pool, "overflow", lambda: -1)(),
    }
