from datetime import datetime, timezone


def utcnow() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(timezone.utc)

def now() -> datetime:
    """Alias for utcnow()."""
    return utcnow()
