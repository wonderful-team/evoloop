from typing import Any

from pydantic import BaseModel, ConfigDict

from app.infrastructure.pydantic_base import DynamicBaseModel


class EvoCloudProxyResponse(DynamicBaseModel):
    """Generic transparent proxy response from EvoCloud / Member Center APIs."""
    code: int = -1
    message: str | None = None
    data: Any | None = None
    success: bool | None = None


class LoginResult(DynamicBaseModel):
    """Enriched login result from EvoCloud auth methods."""

    success: bool
    token: str | None = None
    member_id: int | None = None
    data: dict[str, Any] | None = None
    message: str | None = None


class MemberBenefitsResponse(DynamicBaseModel):
    code: int = 0
    data: dict[str, Any] | None = None


class CacheInvalidateResponse(DynamicBaseModel):
    code: int = 0
    message: str
