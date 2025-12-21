from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm

from app import crud
from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.core import security
from app.core.config import settings
from app.core.security import get_password_hash
from app.models import Message, NewPassword, Token, UserPublic
from app.utils import (
    generate_password_reset_token,
    generate_reset_password_email,
    send_email,
    verify_password_reset_token,
)

router = APIRouter(tags=["login"])


@router.post("/login/access-token")
async def login_access_token(
    session: SessionDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    # 1. Try Remote Login (Imagicbox)
    from app.infrastructure.external.imagicbox import imagicbox_client
    from app.models import UserCreate
    
    remote_result = imagicbox_client.login(form_data.username, form_data.password)
    
    if remote_result.get("success"):
        # Remote login successful
        
        # --- EvoLoop: Auto-connect to Cloud on Login ---
        try:
            from app.infrastructure.evoloop_link.client import init_evoloop_client, get_evoloop_client
            from app.core.config import settings as app_settings
            import asyncio
            from app.logging import logger
            # We can't import router logic easily, so duplicate handler setup or refactor.
            # Let's reuse the simple init logic.
            
            token = remote_result.get("token")
            if token:
                logger.info(f"[EvoLoop] Auto-connecting to cloud with token from login...")
                # Stop existing if any
                existing = get_evoloop_client()
                if existing:
                    existing.stop()
                
                # Init new
                new_client = init_evoloop_client(token=token, device_name=app_settings.EVOLOOP_DEVICE_NAME)
                
                # Reuse handler logic - ideally this should be a shared utility function
                # For now, duplicate standard handler logic to ensure it works
                
                # Use shared handler
                from app.infrastructure.evoloop_link.handler import handle_remote_command

                new_client.set_command_handler(handle_remote_command)
                
                # URL overrides
                if app_settings.EVOLOOP_LINK_BASE_URL:
                    new_client.base_url = app_settings.EVOLOOP_LINK_BASE_URL.rstrip("/")
                if app_settings.EVOLOOP_LINK_WS_URL:
                    new_client.ws_url = app_settings.EVOLOOP_LINK_WS_URL

                # Save token to Redis for auto-recovery on restart
                try:
                    import redis.asyncio as redis
                    redis_client = redis.from_url(app_settings.REDIS_URL, encoding="utf-8", decode_responses=True)
                    async with redis_client:
                         # Set generic token key. Since Backend serves one user primarily in this context (PC Client), 
                         # global key is acceptable. Or use a key structure if multi-user support is needed later.
                         await redis_client.set("evoloop:link:token", token)
                except Exception as e:
                    logger.warning(f"[EvoLoop] Failed to save token to Redis: {e}")

                asyncio.create_task(new_client.start())
        except Exception as e:
            # Don't fail login if cloud connection fails
            from app.logging import logger
            logger.error(f"[EvoLoop] Failed to auto-connect to cloud: {e}")
        # ---------------------------------------------

        user = crud.get_user_by_email(session=session, email=form_data.username)
        if not user:
            # Auto-provision local user if they don't exist
            # Use remote credentials to init local user
            user_in = UserCreate(email=form_data.username, password=form_data.password, full_name=form_data.username)
            user = crud.create_user(session=session, user_create=user_in)
    else:
        # Remote login failed, fallback to local authentication (e.g. for superuser/admin)
        user = crud.authenticate(
            session=session, email=form_data.username, password=form_data.password
        )

    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return Token(
        access_token=security.create_access_token(
            user.id, expires_delta=access_token_expires
        )
    )


@router.post("/login/test-token", response_model=UserPublic)
def test_token(current_user: CurrentUser) -> Any:
    """
    Test access token
    """
    return current_user


@router.post("/password-recovery/{email}")
def recover_password(email: str, session: SessionDep) -> Message:
    """
    Password Recovery
    """
    user = crud.get_user_by_email(session=session, email=email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this email does not exist in the system.",
        )
    password_reset_token = generate_password_reset_token(email=email)
    email_data = generate_reset_password_email(
        email_to=user.email, email=email, token=password_reset_token
    )
    send_email(
        email_to=user.email,
        subject=email_data.subject,
        html_content=email_data.html_content,
    )
    return Message(message="Password recovery email sent")


@router.post("/reset-password/")
def reset_password(session: SessionDep, body: NewPassword) -> Message:
    """
    Reset password
    """
    email = verify_password_reset_token(token=body.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid token")
    user = crud.get_user_by_email(session=session, email=email)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this email does not exist in the system.",
        )
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    hashed_password = get_password_hash(password=body.new_password)
    user.hashed_password = hashed_password
    session.add(user)
    session.commit()
    return Message(message="Password updated successfully")


@router.post(
    "/password-recovery-html-content/{email}",
    dependencies=[Depends(get_current_active_superuser)],
    response_class=HTMLResponse,
)
def recover_password_html_content(email: str, session: SessionDep) -> Any:
    """
    HTML Content for Password Recovery
    """
    user = crud.get_user_by_email(session=session, email=email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this username does not exist in the system.",
        )
    password_reset_token = generate_password_reset_token(email=email)
    email_data = generate_reset_password_email(
        email_to=user.email, email=email, token=password_reset_token
    )

    return HTMLResponse(
        content=email_data.html_content, headers={"subject:": email_data.subject}
    )
