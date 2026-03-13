from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser
from app.core.evocloud import evocloud_manager
from app.models import User, UserPublic

router = APIRouter(prefix="/users", tags=["users"])


# --- Request Schemas ---


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, description="Current password")
    new_password: str = Field(..., min_length=8, description="New password (min 8 characters)")


class UpdateUserRequest(BaseModel):
    nickname: str | None = Field(None, description="User nickname")
    headimg: str | None = Field(None, description="Avatar URL")
    email: str | None = Field(None, description="Email address")


# --- Response Schemas ---


class MessageResponse(BaseModel):
    message: str


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    # The current_user is already populated by get_current_user dependency
    # which fetches data from Member Center
    return current_user


@router.put("/password", response_model=MessageResponse)
async def change_password(
    data: ChangePasswordRequest,
    current_user: CurrentUser,
) -> Any:
    """
    Change current user's password.
    Requires old password for verification.
    """
    result = await evocloud_manager.api.change_password(
        old_password=data.old_password,
        new_password=data.new_password,
    )

    if result.get("code", -1) < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Failed to change password"),
        )

    return {"message": "Password changed successfully"}


@router.put("/me", response_model=UserPublic)
async def update_user_me(
    data: UpdateUserRequest,
    current_user: CurrentUser,
) -> Any:
    """
    Update current user information.
    Only updates fields that are provided.
    """
    # Build update data from non-None fields
    update_data: dict[str, Any] = {}
    if data.nickname is not None:
        update_data["nickname"] = data.nickname
    if data.headimg is not None:
        update_data["headimg"] = data.headimg
    if data.email is not None:
        update_data["email"] = data.email

    if not update_data:
        # No fields to update, return current user
        return current_user

    result = await evocloud_manager.api.update_user_info(update_data)

    if result.get("code", -1) < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Failed to update user info"),
        )

    # Return updated user info from Member Center
    updated_info = await evocloud_manager.api.get_user_info()
    if updated_info.get("code", -1) >= 0:
        data = updated_info.get("data", {})
        return User(
            id=data.get("member_id", current_user.id),
            username=data.get("username", current_user.username),
            email=data.get("email", current_user.email),
            mobile=data.get("mobile", current_user.mobile),
            nickname=data.get("nickname", current_user.nickname),
            headimg=data.get("headimg", current_user.headimg),
            member_level=data.get("member_level", current_user.member_level),
            member_level_name=data.get("member_level_name", current_user.member_level_name),
            level_expire_time=data.get("level_expire_time", current_user.level_expire_time),
            balance=data.get("balance", current_user.balance),
            balance_money=data.get("balance_money", current_user.balance_money),
            point=data.get("point", current_user.point),
            is_active=data.get("is_active", current_user.is_active),
            is_superuser=current_user.is_superuser,
        )

    # Fallback to current user if fetch fails
    return current_user
