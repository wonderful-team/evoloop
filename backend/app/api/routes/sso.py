"""SSO — Member Center 后台 → evoloop 免登（单用户 / 多租户统一）。

iframe 链路：矩阵后台颁发一次性 sso_code → 前端加载时检测 URL 上的 evosso 参数 →
调用本端点以 S2S 凭证兑换 member token → 前端存储并直出聊天界面。

- 多租户模式：token 仅返回给前端（随请求携带），不落全局会话
- 单用户模式：同时写入本地 identity store（API 认证回退依赖）
"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.schemas.responses import DataResponse
from app.core.config import settings
from app.core.events.publishers import publish_user_logged_in
from app.core.evocloud import evocloud_manager
from app.core.identity import identity_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sso"])


class SsoAcceptRequest(BaseModel):
    sso_code: str


@router.post("/accept-token")
async def accept_sso_token(req: SsoAcceptRequest) -> DataResponse:
    """凭一次性 sso_code 兑换 member token（60s 有效，单次使用）。"""
    gateway_key = settings.EVOCLOUD_SSO_KEY
    if not gateway_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="EVOCLOUD_SSO_KEY is not configured",
        )

    result = await evocloud_manager.api.redeem_sso_code(req.sso_code, gateway_key)
    if result.code != 0:
        logger.warning(f"SSO redeem failed: {result.message}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired sso_code",
        )

    data = result.data or {}
    token = data.get("token")
    refresh_token = data.get("refresh_token") or None
    member_id = data.get("member_id")
    if not token or not member_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SSO redeem returned incomplete payload",
        )

    if not settings.MULTI_TENANT_MODE:
        await identity_service.set_token(token, refresh_token)
        await identity_service.store.save_member_id(int(member_id))
        await publish_user_logged_in(token=token, member_id=int(member_id))

    return DataResponse(
        message="ok",
        data={
            "access_token": token,
            "refresh_token": refresh_token or "",
            "member_id": int(member_id),
        },
    )
