from typing import Any

from pydantic import BaseModel, ConfigDict

from app.utils.model_helpers import LegacyDictMixin


class EvoCloudProxyResponse(BaseModel, LegacyDictMixin):
    """Generic transparent proxy response from EvoCloud / Member Center APIs."""

    model_config = ConfigDict(extra="allow")
    code: int = -1
    message: str | None = None
    data: Any | None = None
    success: bool | None = None


class LoginResult(BaseModel, LegacyDictMixin):
    """Enriched login result from EvoCloud auth methods."""

    success: bool
    token: str | None = None
    member_id: int | None = None
    data: dict[str, Any] | None = None
    message: str | None = None


class MemberBenefitsResponse(BaseModel, LegacyDictMixin):
    code: int = 0
    data: dict[str, Any] | None = None


class CacheInvalidateResponse(BaseModel, LegacyDictMixin):
    code: int = 0
    message: str
