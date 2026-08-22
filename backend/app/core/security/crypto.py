"""Cryptographic and token helpers used by security-sensitive code."""

from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

# Optional imports
try:
    import jwt
    from passlib.context import CryptContext

    HAS_JWT = True
except ImportError:
    HAS_JWT = False
    jwt = None  # type: ignore[assignment]

# Try to import settings, fallback if not available
try:
    from app.core.config import settings

    HAS_SETTINGS = True
except (ImportError, Exception):
    # Exception covers Pydantic validation errors in test environment
    HAS_SETTINGS = False
    settings = None  # type: ignore[assignment]

if HAS_JWT:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
else:
    pwd_context = None

ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    """Create a JWT access token signed with ``settings.SECRET_KEY``."""
    if not HAS_JWT or not HAS_SETTINGS:
        raise ImportError("JWT and settings are required for token creation")
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    if not HAS_JWT:
        raise ImportError("passlib is required for password verification")
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a bcrypt password hash."""
    if not HAS_JWT:
        raise ImportError("passlib is required for password hashing")
    return pwd_context.hash(password)


def generate_hmac_signature(secret: str, message: str, hash_alg: str = "sha256") -> str:
    """
    Generate HMAC signature for a message.

    Used for API request signing (e.g. EvoCloud).
    """
    if not secret:
        return ""
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hash_alg).hexdigest()
