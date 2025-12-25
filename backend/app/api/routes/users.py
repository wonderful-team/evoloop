from typing import Any

from fastapi import APIRouter
from app.api.deps import CurrentUser
from app.models import UserPublic

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    # The current_user is already populated by get_current_user dependency 
    # which fetches data from Member Center
    return current_user
