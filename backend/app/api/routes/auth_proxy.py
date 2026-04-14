from fastapi import APIRouter

from app.core.evocloud import evocloud_manager
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.auth import EvoCloudProxyResponse, LoginResult

router = APIRouter()

# --- Schemas ---


class AuthProxyMobileCodeRequest(DynamicBaseModel):
    mobile: str
    captcha_id: str
    captcha_code: str
    type: str = "login"


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


class LoginMobileRequest(DynamicBaseModel):
    mobile: str
    key: str
    code: str


class ResetPasswordMobileRequest(DynamicBaseModel):
    mobile: str
    key: str
    code: str
    password: str


class CheckMobileRequest(DynamicBaseModel):
    mobile: str


# --- Endpoints ---


@router.post("/captcha/config")
async def get_captcha_config() -> EvoCloudProxyResponse:
    """Get Captcha Configuration"""
    return await evocloud_manager.api.get_captcha_config()


@router.get("/captcha/{captcha_id}")
async def get_captcha(captcha_id: str) -> EvoCloudProxyResponse:
    """Get Captcha Image"""
    return await evocloud_manager.api.get_captcha(captcha_id)


@router.get("/register/config")
async def get_register_config() -> EvoCloudProxyResponse:
    """Get Registration Config"""
    return await evocloud_manager.api.get_register_config()


@router.get("/register/agreement")
async def get_register_agreement() -> EvoCloudProxyResponse:
    """Get Registration Agreement"""
    return await evocloud_manager.api.get_register_agreement()


@router.post("/sms/send")
async def send_sms(req: AuthProxyMobileCodeRequest) -> EvoCloudProxyResponse:
    """Send Mobile Verification Code"""
    return await evocloud_manager.api.send_mobile_code(
        req.mobile,
        req.captcha_id,
        req.captcha_code,
        req.type,
    )


@router.post("/register/mobile")
async def register_mobile(req: RegisterMobileRequest) -> EvoCloudProxyResponse:
    """Register with Mobile"""
    return await evocloud_manager.api.register_mobile(req.model_dump(exclude_none=True))


@router.post("/register/username")
async def register_username(req: RegisterUsernameRequest) -> EvoCloudProxyResponse:
    """Register with Username/Password"""
    return await evocloud_manager.api.register_username(req.model_dump(exclude_none=True))


@router.post("/login/mobile")
async def login_mobile(req: LoginMobileRequest) -> LoginResult:
    """Login with Mobile Code"""
    return await evocloud_manager.api.login_mobile(req.mobile, req.key, req.code)


@router.post("/mobile/check")
async def check_mobile(req: CheckMobileRequest) -> EvoCloudProxyResponse:
    """Check if mobile is registered"""
    return await evocloud_manager.api.check_mobile_exist(req.mobile)


@router.post("/password/reset/mobile")
async def reset_password(req: ResetPasswordMobileRequest) -> EvoCloudProxyResponse:
    """Reset password with Mobile Code"""
    return await evocloud_manager.api.reset_password_by_mobile(req.mobile, req.code, req.key, req.password)
