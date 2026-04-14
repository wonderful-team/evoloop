import logging
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.infrastructure.pydantic_base import DynamicBaseModel

from app.api.deps import CurrentUser, TokenDep
from app.core.evocloud import evocloud_manager
from app.core.identity import identity_service
from app.models import User, UserPublic
from app.models.schemas.auth import CacheInvalidateResponse, EvoCloudProxyResponse, MemberBenefitsResponse
from app.services.benefit_service import benefit_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["member"])


# --- Request/Response Schemas ---

class ChangePasswordRequest(DynamicBaseModel):
    old_password: str = Field(..., min_length=1, description="Current password")
    new_password: str = Field(..., min_length=8, description="New password (min 8 characters)")


class UpdateUserRequest(DynamicBaseModel):
    nickname: str | None = Field(None, description="User nickname")
    headimg: str | None = Field(None, description="Avatar URL")
    email: str | None = Field(None, description="Email address")


class MessageResponse(BaseAPIResponse):
    pass


# --- User Profile (Unified) ---

def _parse_int_safe(value: Any, default: int = 0) -> int:
    """Safely parse a value to int, handling strings and edge cases."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value) if value.strip() else default
        except ValueError:
            return default
    return default


def _map_mc_user_to_user(data: dict) -> User:
    """
    将 Member Center /api/member/info 返回的数据映射到 User 模型
    字段与 Member Center 保持对齐
    """
    return User(
        # Core identification
        id=data.get("member_id"),
        username=data.get("username"),
        nickname=data.get("nickname"),
        mobile=data.get("mobile"),
        email=data.get("email"),
        headimg=data.get("headimg"),

        # Member level
        member_level=data.get("member_level", 0),
        member_level_name=data.get("member_level_name"),
        member_level_type=data.get("member_level_type", 0),
        level_expire_time=data.get("level_expire_time", 0),

        # Member labels (handle string values like ",")
        member_label=_parse_int_safe(data.get("member_label"), 0),
        member_label_name=data.get("member_label_name"),
        member_code=data.get("member_code"),

        # Account assets
        point=data.get("point", 0),
        balance=float(data.get("balance", 0) or 0),
        balance_money=float(data.get("balance_money", 0) or 0),
        growth=data.get("growth", 0),

        # Status flags
        status=data.get("status", 1),
        has_password=bool(data.get("password", 0)),
        is_edit_username=data.get("is_edit_username", 0),
        is_fenxiao=data.get("is_fenxiao", 0),

        # Profile
        realname=data.get("realname"),
        sex=data.get("sex", 0),
        birthday=str(data.get("birthday")) if data.get("birthday") and data.get("birthday") != 0 else None,

        # Referral
        source_member=data.get("source_member", 0),

        # Address
        province_id=data.get("province_id", 0),
        city_id=data.get("city_id", 0),
        district_id=data.get("district_id", 0),
        address=data.get("address"),
        full_address=data.get("full_address"),
        longitude=float(data.get("longitude", 0) or 0),
        latitude=float(data.get("latitude", 0) or 0),

        # Third-party
        wx_openid=data.get("wx_openid"),
        wx_unionid=data.get("wx_unionid"),

        # Compatibility
        is_active=data.get("status") == 1,
    )


@router.get("/me", response_model=UserPublic)
async def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user info from Member Center.
    Fields are aligned with Member Center /api/member/info response.
    """
    try:
        result = await evocloud_manager.api.get_user_info()
        if result.get("code") == 0:
            data = result.get("data", {})
            return _map_mc_user_to_user(data)
        else:
            logger.warning(f"Failed to get user info from MC: {result.get('message')}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user info from MC: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )


@router.put("/password", response_model=MessageResponse)
async def change_password(
    data: ChangePasswordRequest,
    current_user: CurrentUser,
) -> EvoCloudProxyResponse:
    """
    Change current user's password (Transparent Proxy).
    """
    return await evocloud_manager.api.change_password(
        old_password=data.old_password,
        new_password=data.new_password,
    )


@router.put("/me", response_model=UserPublic)
async def update_user_me(
    data: UpdateUserRequest,
    current_user: CurrentUser,
) -> EvoCloudProxyResponse:
    """
    Update current user information (Transparent Proxy).
    """
    update_data = data.model_dump(exclude_none=True)
    return await evocloud_manager.api.update_user_info(update_data)


# --- Account Cancellation ---

@router.get("/cancellation/info")
async def get_cancellation_info(_token: TokenDep) -> EvoCloudProxyResponse:
    return await evocloud_manager.api.get_cancellation_info()


@router.post("/cancellation/apply")
async def apply_cancellation(_token: TokenDep) -> EvoCloudProxyResponse:
    return await evocloud_manager.api.apply_cancellation()


@router.post("/cancellation/cancel")
async def cancel_cancellation(_token: TokenDep) -> EvoCloudProxyResponse:
    return await evocloud_manager.api.cancel_cancellation_apply()


# --- Batch Benefits & Cache Management ---

class BatchCheckRequest(DynamicBaseModel):
    benefit_codes: List[str]


class BatchCheckResponse(BaseAPIResponse):
    results: dict[str, bool]
    is_expired: bool
    level_name: str


@router.post("/benefits/check-batch", response_model=BatchCheckResponse)
async def check_benefits_batch(req: BatchCheckRequest, token: TokenDep):
    """
    批量检查多项权益
    
    性能优化：只查询一次API，同时检查多个权益
    """
    # 批量检查权益
    results = await benefit_service.check_multiple_benefits(req.benefit_codes, token)
    
    # 获取额外信息
    benefits_data = await benefit_service.get_member_entitlements(identity_service.get_member_id(token), token)
    
    return BatchCheckResponse(
        results=results,
        is_expired=benefits_data.get("is_expired", False),
        level_name=benefits_data.get("level_name", "免费用户")
    )


@router.get("/benefits")
async def get_member_benefits_api(
    force_refresh: bool = False,
    token: TokenDep = None
) -> MemberBenefitsResponse:
    """
    获取会员完整权益信息
    
    Args:
        force_refresh: 是否强制刷新缓存
    """
    data = await benefit_service.get_member_entitlements(
        identity_service.get_member_id(token), 
        token=token,
        force_refresh=force_refresh
    )
    return MemberBenefitsResponse(code=0, data=data)


@router.post("/benefits/cache/invalidate")
async def invalidate_member_benefits_cache(token: TokenDep) -> CacheInvalidateResponse:
    """
    手动使权益缓存失效（用于调试或强制刷新）
    """
    benefit_service.invalidate_cache(identity_service.get_member_id(token))
    return CacheInvalidateResponse(code=0, message="缓存已清除")
