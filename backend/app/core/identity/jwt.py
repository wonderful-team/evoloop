from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, ConfigDict
from app.utils.model_helpers import LegacyDictMixin

import jwt

from app.core.config import settings

ALGORITHM = "HS256"


class JwtPayload(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")
    sub: str | None = None
    user_id: str | None = None
    device_id: str | None = None
    exp: datetime | None = None


def create_local_jwt(data: JwtPayload, expires_delta: timedelta | None = None) -> str:
    """
    Create a JWT for local desktop frontend sessions.
    """
    to_encode = data.model_dump(exclude_none=True)
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_local_jwt(token: str) -> JwtPayload | None:
    """
    Decode and validate a local JWT.
    """
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return JwtPayload.model_validate(decoded_token)
    except jwt.PyJWTError:
        return None
