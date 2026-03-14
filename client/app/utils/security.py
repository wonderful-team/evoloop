import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def generate_hmac_signature(secret: str, message: str, hash_alg=hashlib.sha256) -> str:
    """
    Generate HMAC signature for a message.
    Used for API request signing (e.g. EvoCloud).
    """
    if not secret:
        return ""
    return hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hash_alg
    ).hexdigest()
