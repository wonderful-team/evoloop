"""API schemas for auth_proxy routes."""

from pydantic import model_validator

from app.infrastructure.pydantic_base import DynamicBaseModel


class RegisterMobileRequest(DynamicBaseModel):
    mobile: str
    key: str
    code: str
    captcha_id: str | None = None
    captcha_code: str | None = None


class RegisterUsernameRequest(DynamicBaseModel):
    username: str | None = None
    email: str | None = None
    full_name: str | None = None
    password: str
    captcha_id: str | None = None
    captcha_code: str | None = None

    @model_validator(mode='after')
    def check_username(self) -> 'RegisterUsernameRequest':
        if not self.username and self.email:
            self.username = self.email
        if not self.username:
            raise ValueError('username or email is required')
        return self


class ResetPasswordMobileRequest(DynamicBaseModel):
    mobile: str
    key: str
    code: str
    password: str


class CheckMobileRequest(DynamicBaseModel):
    mobile: str
