from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
import httpx

from app.core.config import settings
from app.models import Token

router = APIRouter(tags=["login"])

@router.post("/login/access-token")
async def login_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    """
    OAuth2 compatible token login, proxied to Member Center.
    """
    # Member Center Login API (Assuming standard Niushop V5/V6 or provided structure)
    # Typically: POST /api/login/login (or similar)
    # We need to adapt the form_data (username, password) to Member Center's expected format.
    
    base_url = str(settings.IMAGICBOX_API_URL).rstrip('/')
    
    # Try username/password login
    try:
        async with httpx.AsyncClient() as client:
            # Different systems have different login endpoints. 
            # Adjusting for common Niushop patterns: /api/login/login
            response = await client.post(
                f"{base_url}/api/login/login",
                json={
                    "username": form_data.username,
                    "password": form_data.password,
                    # Some systems need 'account' instead of 'username'
                },
                timeout=10.0
            )
            
            # If standard login fails, try alias or different structure if needed.
            # For now assuming this structure.
            
            print(f"DEBUG: Member Center Response Status: {response.status_code}")
            print(f"DEBUG: Member Center Response Body: {response.text}")
            
            if response.status_code != 200:
                print(f"ERROR: Upstream returned {response.status_code}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Incorrect email or password",
                )
            
            data = response.json()
            
            # Check business code
            # Niushop success code is >= 0 (usually 0 or 1)
            if data.get("code", -1) < 0:
                print(f"ERROR: Upstream business code error: {data}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=data.get("message", "Login failed"),
                )
                
            # Extract token. Structure depends on Member Center response.
            # Assuming data['data']['token'] exists.
            token_str = data.get("data", {}).get("token")
            if not token_str:
                 raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Token not found in response",
                )
            
            return Token(access_token=token_str, token_type="bearer")

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to connect to Member Center: {exc}",
        )
