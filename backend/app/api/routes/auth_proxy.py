from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.infrastructure.external.imagicbox import imagicbox_client

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
    captcha_id: Optional[str] = None
    captcha_code: Optional[str] = None

class RegisterUsernameRequest(BaseModel):
    username: str
    password: str
    captcha_id: Optional[str] = None
    captcha_code: Optional[str] = None
    
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

@router.get("/captcha/config")
async def get_captcha_config() -> Any:
    """Get Captcha Configuration"""
    return await imagicbox_client.get_captcha_config()

@router.get("/captcha/get")
async def get_captcha(id: Optional[str] = None) -> Any:
    """Get Captcha Image"""
    # id is query param
    return await imagicbox_client.get_captcha(id if id else "")

@router.get("/register/config")
async def get_register_config() -> Any:
    """Get Registration Config"""
    return await imagicbox_client.get_register_config()

@router.get("/register/agreement")
async def get_register_agreement() -> Any:
    """Get Registration Agreement"""
    return await imagicbox_client.get_register_agreement()

@router.post("/sms/send")
async def send_mobile_code(req: MobileCodeRequest) -> Any:
    """Send Mobile Verification Code"""
    return await imagicbox_client.send_mobile_code(req.mobile, req.captcha_id, req.captcha_code, req.type)

@router.post("/register/mobile")
async def register_mobile(req: RegisterMobileRequest) -> Any:
    """Register with Mobile"""
    data = req.dict()
    return await imagicbox_client.register_mobile(data)

@router.post("/register/account")
async def register_username(req: RegisterUsernameRequest) -> Any:
    """Register with Username/Password"""
    data = req.dict()
    return await imagicbox_client.register_username(data)

@router.post("/login/mobile")
async def login_mobile(req: LoginMobileRequest) -> Any:
    """Login with Mobile Code"""
    return await imagicbox_client.login_mobile(req.mobile, req.key, req.code)

@router.get("/mobile/check")
async def check_mobile(mobile: str) -> Any:
    """Check if mobile is registered"""
    return await imagicbox_client.check_mobile_exist(mobile)

@router.get("/config/global")
async def get_global_config():
    """Get global config (servicer info etc)"""
    return await imagicbox_client.get_ai_global_config()

@router.post("/password/reset/mobile")
async def reset_password_mobile(req: ResetPasswordMobileRequest) -> Any:
    """Reset password with Mobile Code"""
    data = req.dict()
    return await imagicbox_client.reset_password_by_mobile(req.mobile, req.code, req.key, req.password)
