import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import Field

from app.api.responses import BaseAPIResponse
from app.core.evocloud import evocloud_manager
from app.core.identity import identity_service
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models import Token
from app.models.schemas.auth import EvoCloudProxyResponse
from app.api.schemas.account import MobileCodeRequest, MobileLoginRequest, MobileCodeResponse, WeChatConfigResponse, WeChatQRResponse, WeChatStatusResponse, LogoutResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["account"])

# --- Request / Response Schemas ---

# --- Internal Helpers ---

async def _member_center_request(method: str, endpoint: str, **kwargs) -> EvoCloudProxyResponse:
    """Make request to Member Center API using EvoCloud client."""
    return EvoCloudProxyResponse.model_validate(await evocloud_manager.api.request(method, endpoint, **kwargs))


# --- Username/Password Login (Proxied) ---

@router.post("/login/access-token", response_model=Token)
async def login_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """
    Passthrough login to Member Center using username and password.
    Returns the access token directly.
    """
    result = await evocloud_manager.api.login(form_data.username, form_data.password)

    if not result.get("success", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Incorrect username or password"),
        )

    token = result.get("token")
    member_id = result.get("member_id")
    if not token:
        raise HTTPException(status_code=500, detail="Session missing token")

    # Save access token and member_id to local store
    await identity_service.login_with_cloud_result(result)
    
    return Token(access_token=token, token_type="bearer")


# --- Mobile Login (New Routines) ---

@router.post("/login/mobile/code")
async def request_mobile_code(req: MobileCodeRequest) -> MobileCodeResponse:
    """
    Request an SMS verification code via Member Center.
    """
    result = await evocloud_manager.api.send_mobile_code(
        mobile=req.mobile,
        captcha_id=req.captcha_id or "",
        captcha_code=req.captcha_code or "",
        type="login"
    )
    
    if result.get("code", -1) != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Failed to send verification code"),
        )
        
    return MobileCodeResponse(
        code=0,
        message="Verification code sent",
        key=result.get("data", {}).get("key")
    )


@router.post("/login/mobile", response_model=Token)
async def login_mobile(req: MobileLoginRequest):
    """
    Login using phone number and SMS verification code.
    """
    result = await evocloud_manager.api.login_mobile(
        mobile=req.mobile,
        key=req.key,
        code=req.code
    )
    
    if not result.get("success", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Login failed"),
        )
        
    token = result.get("token")
    if not token:
        raise HTTPException(status_code=500, detail="Session missing token")

    # Save access token to local store
    await identity_service.login_with_cloud_result(result)
    
    return Token(access_token=token, token_type="bearer")


# --- WeChat Authentication (Proxied) ---

@router.get("/auth/wechat/config")
async def get_wechat_config() -> WeChatConfigResponse:
    """Get WeChat login configuration from Member Center."""
    try:
        result = await _member_center_request(
            "GET",
            "/wechat/api/wechat/verificationwx",
        )
        is_configured = result.get("code", -1) == 0

        return WeChatConfigResponse(enabled=is_configured, app_id=None)
    except Exception as e:
        logger.warning(f"Failed to check WeChat config: {e}")
        return WeChatConfigResponse(enabled=False, app_id=None)


@router.post("/auth/wechat/qrcode")
async def generate_qr_code() -> WeChatQRResponse:
    """Generate a QR code for WeChat login via Member Center."""
    try:
        result = await _member_center_request(
            "POST",
            "/wechat/api/wechat/logincode",
        )

        if result.get("code", -1) != 0:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Failed to generate QR code"),
            )

        data = result.get("data", {})
        return WeChatQRResponse(
            key=data.get("key"),
            expire_time=data.get("expire_time", 600),
            qrcode_url=data.get("qrcode"),
            ticket=data.get("ticket", ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate QR code",
        )


@router.get("/auth/wechat/status")
async def check_wechat_login_status(
    key: Annotated[str, Query(description="The unique key from QR code generation")],
) -> WeChatStatusResponse:
    """Check the login status for a given QR code key via Member Center."""
    try:
        result = await _member_center_request(
            "POST",
            "/api/login/checklogin",
            data={"key": key},
        )

        if result.get("code", -1) < 0:
            return WeChatStatusResponse(
                status="expired",
                message=result.get("message", "QR code expired"),
            )

        data = result.get("data", {})
        token = data.get("token")

        if token:
            return WeChatStatusResponse(
                status="confirmed",
                message="Login successful",
                access_token=token,
                token_type="bearer",
            )
        else:
            return WeChatStatusResponse(
                status="pending",
                message="Waiting for scan",
            )
    except Exception as e:
        logger.error(f"Failed to check login status: {e}")
        return WeChatStatusResponse(status="error", message="Failed to check status")


@router.post("/auth/wechat/login-direct", response_model=Token)
async def wechat_direct_login(
    key: Annotated[str, Query(description="The unique key from QR code generation")],
):
    """
    Returns the cloud access token directly after successful WeChat scan.
    """
    try:
        result = await _member_center_request(
            "POST",
            "/api/login/checklogin",
            data={"key": key},
        )

        if result.get("code", -1) != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Login failed"),
            )

        data = result.get("data", {})
        member_center_token = data.get("token")

        if not member_center_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Login not completed")

        member_id = data.get("member_id") or data.get("id")
        if not member_id:
            raise HTTPException(status_code=500, detail="Cloud session missing member_id")

        # Save access token to local store
        from app.models.schemas.auth import LoginResult
        await identity_service.login_with_cloud_result(
            LoginResult(success=True, token=member_center_token, member_id=int(member_id), data=data)
        )
        return Token(access_token=member_center_token, token_type="bearer")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WeChat login failed: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@router.post("/auth/wechat/callback")
async def wechat_callback(
    request: Request,
    signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
):
    """
    WeChat server callback endpoint (Pass-through).
    """
    body = await request.body()
    try:
        result = await _member_center_request(
            "POST",
            "/wechat/api/wechat/callback",
            params={"signature": signature, "timestamp": timestamp, "nonce": nonce},
            data=body,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to forward callback: {e}")
        return {"message": "OK"}


# --- Logout ---

@router.post("/logout")
async def logout() -> LogoutResponse:
    """
    Clear local session and access tokens.
    """
    identity_service.logout()
    return LogoutResponse(code=0, message="Logged out successfully")
