import time
import uuid
from datetime import datetime


def gen_uuid() -> str:
    """Generate a standard UUID4 string."""
    return str(uuid.uuid4())


def gen_uuid_hex() -> str:
    """Generate a UUID4 hex string (no dashes, 32 chars)."""
    return uuid.uuid4().hex


def gen_short_id() -> str:
    """Generate a short unique ID (first 8 chars of UUID)."""
    return gen_uuid()[:8]


def unique_id(label: str, *parts: object, use_ms: bool = False) -> str:
    """Build a collision-resistant ID: ``<label>[-<part>...]-<epoch>``.

    Epoch is seconds (or milliseconds when ``use_ms=True``), so sequential
    calls remain unique within a process.

    >>> unique_id("req", thread_id)
    'req-s0-1690000000'
    """
    epoch = int(time.time() * 1000) if use_ms else int(time.time())
    if parts:
        return "-".join((label, *(str(p) for p in parts), str(epoch)))
    return f"{label}-{epoch}"


def stamped_id(label: str = "", dt: datetime | None = None) -> str:
    """Build a timestamp id: ``<label>_<YYYYMMDD_HHMMSS>``.

    ``dt`` defaults to now; an empty label yields the bare timestamp.
    """
    value = (dt if dt is not None else datetime.now()).strftime("%Y%m%d_%H%M%S")
    return f"{label}_{value}" if label else value
