import time
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(timezone.utc)


def elapsed_ms(start: float, end: float | None = None) -> float:
    """Wall-clock milliseconds between ``start`` and ``end`` (defaults to now)."""
    return ((end if end is not None else time.time()) - start) * 1000


def ts_from_dt(dt: datetime | None, default: int = 0) -> int:
    """Safely convert a naive-UTC or tz-aware datetime to Unix timestamp.

    Handles naive datetimes (from SQLite) by treating them as UTC,
    and passes tz-aware datetimes through correctly.

    Args:
        dt: Datetime value (naive UTC or tz-aware).
        default: Fallback value if dt is None.

    Returns:
        Unix timestamp (int).
    """
    if dt is None:
        return default
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def now() -> datetime:
    """Alias for utcnow()."""
    return utcnow()


# ============================================================================
# Timestamp Normalization
# ============================================================================


def normalize_timestamp_ms_to_sec(timestamp_ms: float | None) -> float:
    """
    Convert timestamp from milliseconds to seconds.

    Args:
        timestamp_ms: Timestamp in milliseconds (e.g., 12345.6)

    Returns:
        Timestamp in seconds (e.g., 12.3456)
    """
    if timestamp_ms is None:
        return 0.0
    return float(timestamp_ms) / 1000.0


# ============================================================================
# ISO Timestamp Parsing
# ============================================================================


def parse_iso_timestamp(iso_string: str) -> datetime | None:
    """
    Parse ISO 8601 timestamp string to datetime.

    Args:
        iso_string: ISO 8601 formatted timestamp

    Returns:
        Parsed datetime or None if parsing fails
    """
    try:
        # Try with timezone
        return datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        try:
            # Try without timezone
            return datetime.fromisoformat(iso_string)
        except (ValueError, AttributeError):
            return None


def format_iso_timestamp(dt: datetime | None = None) -> str:
    """
    Format datetime as ISO 8601 string.

    Args:
        dt: Datetime to format (default: current UTC time)

    Returns:
        ISO 8601 formatted string
    """
    if dt is None:
        dt = utcnow()
    return dt.isoformat()


