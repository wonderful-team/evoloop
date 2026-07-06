import uuid


def gen_uuid() -> str:
    """Generate a standard UUID4 string."""
    return str(uuid.uuid4())


def gen_uuid_hex() -> str:
    """Generate a UUID4 hex string (no dashes, 32 chars)."""
    return uuid.uuid4().hex


def gen_short_id() -> str:
    """Generate a short unique ID (first 8 chars of UUID)."""
    return gen_uuid()[:8]
