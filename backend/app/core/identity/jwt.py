import jwt
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from app.core.config import settings

ALGORITHM = "HS256"


def create_local_jwt(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT for local desktop frontend sessions.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_local_jwt(token: str) -> Optional[dict[str, Any]]:
    """
    Decode and validate a local JWT.
    """
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return decoded_token
    except jwt.PyJWTError:
        return None
