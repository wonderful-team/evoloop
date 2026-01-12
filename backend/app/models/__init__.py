import uuid
from typing import Any

from sqlmodel import Field, SQLModel

from .config import SystemConfig


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(SQLModel):
    sub: str | None = None


# User model reflecting Member Center data structure
# No longer a table=True model
class User(SQLModel):
    id: int | str  # Member Center usually uses integer member_id, but keeping str compat
    username: str | None = None
    email: str | None = None
    mobile: str | None = None
    nickname: str | None = None
    headimg: str | None = None  # Avatar URL

    # Member Center specific fields
    member_level: int = 0
    member_level_name: str | None = None
    level_expire_time: int = 0
    balance: float = 0.0
    balance_money: float = 0.0
    point: int = 0

    is_active: bool = True
    is_superuser: bool = False  # This might need special handling based on Member Center roles or config


class UserPublic(User):
    pass


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int
