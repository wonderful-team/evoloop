import time
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(timezone.utc)


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


def normalize_timestamp_sec_to_ms(timestamp_sec: float | None) -> float:
    """
    Convert timestamp from seconds to milliseconds.
    
    Args:
        timestamp_sec: Timestamp in seconds
    
    Returns:
        Timestamp in milliseconds
    """
    if timestamp_sec is None:
        return 0.0
    return float(timestamp_sec) * 1000.0


def get_relative_timestamp() -> float:
    """
    Get a relative timestamp (seconds since an arbitrary point).
    
    Useful for measuring durations and relative timing.
    """
    return time.time()


# ============================================================================
# Duration Formatting
# ============================================================================


def format_duration(seconds: float) -> str:
    """
    Format seconds into human-readable duration string.
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        Formatted string like "1h 23m 45s", "2m 30s", or "500ms"
    
    Examples:
        >>> format_duration(5025.5)
        '1h 23m 45s'
        >>> format_duration(150.5)
        '2m 30s'
        >>> format_duration(0.5)
        '500ms'
    """
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    
    if seconds < 60:
        return f"{int(seconds)}s"
    
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {secs}s"


def format_duration_iso(seconds: float) -> str:
    """
    Format duration as ISO 8601 duration string.
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        ISO 8601 duration string like "PT1H23M45S"
    """
    td = timedelta(seconds=int(seconds))
    hours, remainder = divmod(td.seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    
    parts = []
    if hours:
        parts.append(f"{hours}H")
    if minutes:
        parts.append(f"{minutes}M")
    if secs or not parts:
        parts.append(f"{secs}S")
    
    return f"PT{''.join(parts)}"


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
        return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
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


# ============================================================================
# Timeout Helpers
# ============================================================================


def has_timed_out(start_time: float, timeout_seconds: float) -> bool:
    """
    Check if timeout has been exceeded.
    
    Args:
        start_time: Start timestamp from time.time()
        timeout_seconds: Timeout duration in seconds
    
    Returns:
        True if timeout exceeded
    """
    return time.time() - start_time > timeout_seconds


def remaining_time(start_time: float, timeout_seconds: float) -> float:
    """
    Calculate remaining time before timeout.
    
    Args:
        start_time: Start timestamp from time.time()
        timeout_seconds: Timeout duration in seconds
    
    Returns:
        Remaining seconds (0 if timeout exceeded)
    """
    elapsed = time.time() - start_time
    return max(0.0, timeout_seconds - elapsed)
