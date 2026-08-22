"""MCP authentication schemas."""

import time
from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class AuthToken(DynamicBaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: float | None = None
    scope: str | None = None

    def is_expired(self) -> bool:
        """判断 token 是否已过期。

        ``expires_in`` 存的是绝对过期时间戳（``time.time() + expires_in``）；
        未设置（None）视为永不过期。
        """
        if self.expires_in is None:
            return False
        return time.time() >= self.expires_in


class AuthConfig(DynamicBaseModel):
    method: str
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str | None = None
    authorization_url: str | None = None
    scope: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ElicitationValues(DynamicBaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class ElicitationField(DynamicBaseModel):
    name: str
    description: str = ""
    required: bool = True
    sensitive: bool = False
    field_type: str = "string"
    default: Any | None = None
    options: list[dict[str, Any]] | None = None


class ElicitationRequest(DynamicBaseModel):
    server_name: str
    fields: list[ElicitationField] = Field(default_factory=list)
    message: str | None = None
