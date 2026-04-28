"""MCP authentication schemas."""

from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class AuthToken(DynamicBaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    scope: str | None = None


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
    label: str
    type: str = "text"
    required: bool = True
    default: Any | None = None
    options: list[dict[str, Any]] | None = None


class ElicitationRequest(DynamicBaseModel):
    server_name: str
    fields: list[ElicitationField] = Field(default_factory=list)
    message: str | None = None
