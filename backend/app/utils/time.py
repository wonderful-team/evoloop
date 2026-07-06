import time
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(timezone.utc)


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


# ============================================================================
# Natural Language Date/Time Parsing
# ============================================================================

import re


def parse_relative_time(time_expr: str | datetime | None, base_time: datetime | None = None) -> datetime | None:
    """
    Parse natural language time expressions into datetime.
    
    Supports multiple input formats:
    - datetime object (pass-through)
    - ISO format: "2023-12-31T23:59:00"
    - Relative time: "1 hour", "30 mins", "2 days", "tomorrow"
    - Chinese: "1小时", "30分钟", "明天"
    - Keywords: "today", "now", "待定", "tbd", "none"
    
    Args:
        time_expr: Time expression in various formats
        base_time: Base time for relative calculations (default: utcnow())
    
    Returns:
        Parsed datetime or None if not specified/TBD
    
    Examples:
        >>> parse_relative_time("2023-12-31T23:59:00")
        datetime(2023, 12, 31, 23, 59)
        >>> parse_relative_time("1 hour")
        datetime(2026, 4, 6, 17, 36)  # 1 hour from now
        >>> parse_relative_time("明天")
        datetime(2026, 4, 7, 16, 36)  # tomorrow
        >>> parse_relative_time("待定")
        None
        >>> parse_relative_time(datetime.now())
        datetime(2026, 4, 6, 16, 36)  # pass-through
    
    Note:
        This is a general-purpose utility. For Todo-specific parsing
        that uses different defaults, wrap this function.
    """
    if not time_expr:
        return None
    
    # If already a datetime, return as-is
    if isinstance(time_expr, datetime):
        return time_expr
    
    time_str = time_expr.lower().strip()
    
    # Keywords that mean "no date"
    if time_str in ["待定", "tbd", "none", "null", "pending", "unset", "", "none"]:
        return None
    
    # Try ISO format first
    parsed = parse_iso_timestamp(time_expr)
    if parsed:
        return parsed
    
    # Relative parsing
    now = base_time or utcnow()
    
    # Hours: (n) hours | (n) hour | (n) hrs | (n) 小时
    match = re.search(r"(\d+)\s*(?:hour|hours|hr|hrs|小时)", time_str)
    if match:
        return now + timedelta(hours=int(match.group(1)))
    
    # Minutes: (n) mins | (n) minutes | (n) min | (n) 分钟 | (n) 分
    match = re.search(r"(\d+)\s*(?:min|mins|minute|minutes|分钟|分)", time_str)
    if match:
        return now + timedelta(minutes=int(match.group(1)))
    
    # Seconds: (n) secs | (n) seconds | (n) sec | (n) 秒
    match = re.search(r"(\d+)\s*(?:sec|secs|second|seconds|秒)", time_str)
    if match:
        return now + timedelta(seconds=int(match.group(1)))
    
    # Days: (n) days | (n) day | (n) 天
    match = re.search(r"(\d+)\s*(?:day|days|天)", time_str)
    if match:
        return now + timedelta(days=int(match.group(1)))
    
    # Weeks: (n) weeks | (n) week | (n) 周 | (n) 星期
    match = re.search(r"(\d+)\s*(?:week|weeks|周|星期)", time_str)
    if match:
        return now + timedelta(weeks=int(match.group(1)))
    
    # Months (approximate): (n) months | (n) month | (n) 个月 | (n) 月
    match = re.search(r"(\d+)\s*(?:months?|个月|月)", time_str)
    if match:
        return now + timedelta(days=30 * int(match.group(1)))
    
    # Years (approximate): (n) years | (n) year | (n) 年
    match = re.search(r"(\d+)\s*(?:years?|年)", time_str)
    if match:
        return now + timedelta(days=365 * int(match.group(1)))
    
    # Special keywords
    if re.search(r"(?:^|\s)(?:tomorrow|明天|明日)(?:\s|$)", time_str):
        return now + timedelta(days=1)
    
    if re.search(r"(?:^|\s)(?:today|今天|今日)(?:\s|$)", time_str):
        return now
    
    if re.search(r"(?:^|\s)(?:now|现在|立即|马上)(?:\s|$)", time_str):
        return now
    
    if re.search(r"(?:^|\s)(?:next week|下周|下星期)(?:\s|$)", time_str):
        return now + timedelta(weeks=1)
    
    if re.search(r"(?:^|\s)(?:next month|下个月|下月)(?:\s|$)", time_str):
        return now + timedelta(days=30)
    
    if re.search(r"(?:^|\s)(?:next year|明年)(?:\s|$)", time_str):
        return now + timedelta(days=365)
    
    # Could not parse
    return None


def is_past(dt: datetime | None, reference: datetime | None = None) -> bool:
    """
    Check if a datetime is in the past.
    
    Args:
        dt: Datetime to check
        reference: Reference time (default: utcnow())
    
    Returns:
        True if dt is in the past, False otherwise (including if dt is None)
    """
    if dt is None:
        return False
    reference = reference or utcnow()
    return dt < reference


def time_until(dt: datetime | None, reference: datetime | None = None) -> timedelta | None:
    """
    Calculate time remaining until a datetime.
    
    Args:
        dt: Target datetime
        reference: Reference time (default: utcnow())
    
    Returns:
        Timedelta until dt, or None if dt is None or in the past
    """
    if dt is None:
        return None
    reference = reference or utcnow()
    if dt <= reference:
        return timedelta(0)
    return dt - reference
