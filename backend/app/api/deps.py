from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.core.member_center import member_center
from app.models import User



def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

SessionDep = Annotated[Session, Depends(get_db)]
# TokenDep = Annotated[str, Depends(reusable_oauth2)]
# TokenDepOptional = Annotated[str | None, Depends(reusable_oauth2_optional)]

# Since we removed OAuth2PasswordBearer, we need another way to get the token.
# Simplest way is to define it manually as a dependency that extracts from header
from fastapi import Header

async def get_token_header(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization:
         raise HTTPException(status_code=401, detail="Missing authorization header")
    if not authorization.startswith("Bearer "):
         raise HTTPException(status_code=401, detail="Invalid authorization header format")
    return authorization.split(" ")[1]

async def get_token_header_optional(authorization: Annotated[str | None, Header()] = None) -> str | None:
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None  # Or raise error if strict
    return authorization.split(" ")[1]

TokenDep = Annotated[str, Depends(get_token_header)]
TokenDepOptional = Annotated[str | None, Depends(get_token_header_optional)]

async def get_current_user(token: TokenDep) -> User:
    try:
        # Pass the token directly to Member Center API
        user_data = await member_center.get_user_info(token)
        
        if user_data:
            user_data["id"] = user_data.get("member_id")
        
        # Map Member Center data to User model
        # Assuming user_data has keys compatible with User model or we map them here
        user = User.model_validate(user_data)
        
        if not user.is_active:
             raise HTTPException(status_code=400, detail="Inactive user")
             
        return user
    except HTTPException as e:
        raise e
    except Exception as e:
        # Log error here if logger is available
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
        )

CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_optional(token: TokenDepOptional) -> User | None:
    if not token:
        return None
    try:
        user_data = await member_center.get_user_info(token)
        user = User.model_validate(user_data)
        if not user.is_active:
            return None
        return user
    except Exception:
        return None

CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]
