"""API schemas for auth_proxy routes."""

from app.infrastructure.pydantic_base import DynamicBaseModel


class RegisterMobileRequest(DynamicBaseModel):
    mobile: str
    key: str
    code: str
    captcha_id: str | None = None
    captcha_code: str | None = None

class RegisterUsernameRequest(DynamicBaseModel):
    username: str
    password: str
    captcha_id: str | None = None
    captcha_code: str | None = None

class ResetPasswordMobileRequest(DynamicBaseModel):
    mobile: str
    key: str
    code: str
    password: str

class CheckMobileRequest(DynamicBaseModel):
    mobile: str
