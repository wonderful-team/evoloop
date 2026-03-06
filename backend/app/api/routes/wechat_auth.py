"""WeChat authentication routes for QR code login.

This module acts as a proxy to Member Center's WeChat login APIs.
Member Center handles the actual WeChat integration.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.core.evocloud import evocloud_manager
from app.core.identity import identity_service
from app.models import Token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wechat-auth"])


async def _member_center_request(method: str, endpoint: str, **kwargs) -> dict:
    """Make request to Member Center API using EvoCloud client."""
    return await evocloud_manager.api.request(method, endpoint, **kwargs)


@router.get("/auth/wechat/config")
async def get_wechat_config():
    """Get WeChat login configuration from Member Center."""
    try:
        # Check if WeChat is configured in Member Center
        result = await _member_center_request(
            "GET",
            "/wechat/api/wechat/verificationwx",
        )
        # Member Center returns code 0 for success
        is_configured = result.get("code", -1) == 0

        return {
            "enabled": is_configured,
            "app_id": None,  # Don't expose app_id for security
        }
    except Exception as e:
        logger.warning(f"Failed to check WeChat config: {e}")
        return {"enabled": False, "app_id": None}


@router.post("/auth/wechat/qrcode")
async def generate_qr_code():
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
        return {
            "key": data.get("key"),
            "expire_time": data.get("expire_time", 600),
            "qrcode_url": data.get("qrcode"),
            "ticket": data.get("ticket", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate QR code",
        )


@router.get("/auth/wechat/status")
async def check_login_status(
    key: Annotated[str, Query(description="The unique key from QR code generation")],
):
    """Check the login status for a given QR code key via Member Center."""
    try:
        result = await _member_center_request(
            "POST",
            "/api/login/checklogin",
            data={"key": key},
        )

        # Member Center returns:
        # - code 0, data.token exists: login successful
        # - code 0, no token: still waiting
        # - code < 0: error or expired

        if result.get("code", -1) < 0:
            return {
                "status": "expired",
                "message": result.get("message", "QR code expired"),
            }

        data = result.get("data", {})
        token = data.get("token")

        if token:
            # Login successful - Member Center returned token
            # Store the token and return success
            return {
                "status": "confirmed",
                "message": "Login successful",
                "access_token": token,
                "token_type": "bearer",
            }
        else:
            # Still waiting for scan
            return {
                "status": "pending",
                "message": "Waiting for scan",
            }

    except Exception as e:
        logger.error(f"Failed to check login status: {e}")
        return {
            "status": "error",
            "message": "Failed to check status",
        }


@router.post("/auth/wechat/login-direct", response_model=Token)
async def wechat_direct_login(
    key: Annotated[str, Query(description="The unique key from QR code generation")],
):
    """
    Complete WeChat login using Member Center token.
    This exchanges the Member Center token for a local JWT.
    """
    try:
        # Check status with Member Center
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Login not completed",
            )

        # Use Member Center token to initialize local session
        # This creates a local JWT that EvoLoop frontend can use
        cloud_result = {
            "success": True,
            "token": member_center_token,
            "data": data,
        }

        local_token = await identity_service.login_with_cloud_result(cloud_result)
        if not local_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create local session",
            )

        return Token(access_token=local_token, token_type="bearer")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WeChat login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}",
        )


@router.get("/auth/wechat/callback")
async def wechat_callback_get(
    request: Request,
    signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str | None = Query(None),
):
    """
    WeChat server callback endpoint - GET verification.
    This is handled by Member Center, but we provide a pass-through if needed.
    """
    # In the current setup, Member Center handles WeChat callbacks directly
    # This endpoint is here for flexibility if needed in the future
    if echostr:
        return echostr
    return {"message": "OK"}


@router.post("/auth/wechat/callback")
async def wechat_callback_post(
    request: Request,
    signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
):
    """
    WeChat server callback endpoint - POST events.
    This is handled by Member Center directly.
    """
    # Read the body
    body = await request.body()

    # Forward to Member Center
    try:
        result = await _member_center_request(
            "POST",
            "/wechat/api/wechat/callback",
            params={
                "signature": signature,
                "timestamp": timestamp,
                "nonce": nonce,
            },
            data=body,  # Use data instead of content
        )
        return result
    except Exception as e:
        logger.error(f"Failed to forward callback: {e}")
        return {"message": "OK"}  # Always return OK to WeChat
