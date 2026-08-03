"""API schemas for account routes."""

from pydantic import Field

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel


class MobileCodeRequest(DynamicBaseModel):
    mobile: str = Field(..., description="Phone number")
    captcha_id: str | None = None
    captcha_code: str | None = None
    type: str = "login"


class MobileLoginRequest(DynamicBaseModel):
    mobile: str = Field(..., description="Phone number")
    code: str = Field(..., description="SMS verification code")
    key: str = Field(..., description="Verification key returned from code request")


class MobileCodeResponse(BaseAPIResponse):
    code: int
    key: str | None = None


class WeChatConfigResponse(BaseAPIResponse):
    enabled: bool
    app_id: str | None = None


class WeChatQRResponse(BaseAPIResponse):
    key: str | None = None
    expire_time: int
    qrcode_url: str | None = None
    ticket: str


class WeChatStatusResponse(BaseAPIResponse):
    status: str
    access_token: str | None = None
    token_type: str | None = None


class LogoutResponse(BaseAPIResponse):
    code: int
