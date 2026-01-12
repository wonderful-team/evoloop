from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.infrastructure.external.evocloud import evocloud_client

router = APIRouter()

# --- Schemas ---

class MobileCodeRequest(BaseModel):
    mobile: str
    captcha_id: str
    captcha_code: str
    type: str = "login"

class RegisterMobileRequest(BaseModel):
    mobile: str
    key: str
    code: str
    captcha_id: str | None = None
    captcha_code: str | None = None

class RegisterUsernameRequest(BaseModel):
    username: str
    password: str
    captcha_id: str | None = None
    captcha_code: str | None = None

class LoginMobileRequest(BaseModel):
    mobile: str
    key: str
    code: str

class ResetPasswordMobileRequest(BaseModel):
    mobile: str
    key: str
    code: str
    password: str


# --- Endpoints ---

@router.post("/captcha/config")
async def get_captcha_config() -> Any:
    """Get Captcha Configuration"""
    return await evocloud_client.get_captcha_config()

@router.get("/captcha/{captcha_id}")
async def get_captcha(captcha_id: str) -> Any:
    """Get Captcha Image"""
    return await evocloud_client.get_captcha(captcha_id)

@router.get("/register/config")
async def get_register_config() -> Any:
    """Get Registration Config"""
    return await evocloud_client.get_register_config()

@router.get("/register/agreement")
async def get_register_agreement() -> Any:
    """Get Registration Agreement"""
    return await evocloud_client.get_register_agreement()

@router.post("/sms/send")
async def send_sms(data: dict) -> Any:
    """Send Mobile Verification Code"""
    return await evocloud_client.send_mobile_code(
        data.get("mobile"),
        data.get("captcha_id"),
        data.get("captcha_code"),
        data.get("type", "login")
    )

@router.post("/register/mobile")
async def register_mobile(data: dict) -> Any:
    """Register with Mobile"""
    return await evocloud_client.register_mobile(data)

@router.post("/register/username")
async def register_username(data: dict) -> Any:
    """Register with Username/Password"""
    return await evocloud_client.register_username(data)

@router.post("/login/mobile")
async def login_mobile(req: LoginMobileRequest) -> Any:
    """Login with Mobile Code"""
    return await evocloud_client.login_mobile(req.mobile, req.key, req.code)

@router.post("/mobile/check")
async def check_mobile(data: dict) -> Any:
    """Check if mobile is registered"""
    return await evocloud_client.check_mobile_exist(data.get("mobile"))

@router.post("/password/reset/mobile")
async def reset_password(data: dict) -> Any:
    """Reset password with Mobile Code"""
    return await evocloud_client.reset_password_by_mobile(req.mobile, req.code, req.key, req.password)
