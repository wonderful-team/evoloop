"""API schemas for member routes."""

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.api.schemas.responses import BaseAPIResponse, ListResponse
from pydantic import Field
from typing import Any, Optional

class ChangePasswordRequest(DynamicBaseModel):
    old_password: str = Field(..., min_length=1, description="Current password")
    new_password: str = Field(..., min_length=8, description="New password (min 8 characters)")

class UpdateUserRequest(DynamicBaseModel):
    nickname: str | None = Field(None, description="User nickname")
    headimg: str | None = Field(None, description="Avatar URL")
    email: str | None = Field(None, description="Email address")

class BatchCheckRequest(DynamicBaseModel):
    benefit_codes: list[str]

class BatchCheckResponse(BaseAPIResponse):
    results: dict[str, bool]
    is_expired: bool
    level_name: str
