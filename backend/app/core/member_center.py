import httpx
from typing import Any, Dict, Optional
from app.core.config import settings
from fastapi import HTTPException, status

class MemberCenterClient:
    def __init__(self):
        self.base_url = str(settings.IMAGICBOX_API_URL).rstrip('/')
        self.api_key = settings.IMAGICBOX_API_KEY
        self.api_secret = settings.IMAGICBOX_API_SECRET

    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """
        Validate token and get user info from Member Center.
        This uses the client's bearer token directly.
        """
        async with httpx.AsyncClient() as client:
            try:
                # Assuming the endpoint is /api/member/member/info based on Niushop structure
                # We pass the Authorization header as is
                # URL Correction: Controller is Member, method is info -> /api/member/info
                url = f"{self.base_url}/api/member/info"
                print(f"DEBUG: Requesting Member Info from: {url}")
                
                response = await client.get(
                    url,
                    # BaseApi.php input() gets params from query string or body. 
                    # checkToken() checks $this->params['token'].
                    # So we must pass token as a query param.
                    params={"token": token},
                    timeout=10.0
                )
                
                print(f"DEBUG: Member Info Status: {response.status_code}")
                # print(f"DEBUG: Member Info Body: {response.text}") # Uncomment if body is needed, identifying 404 is enough usually

                
                if response.status_code == 401:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid token or expired session",
                    )
                
                if response.status_code != 200:
                     raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Member Center API Error: {response.text}",
                    )
                
                data = response.json()
                if data.get("code", -1) < 0:
                     raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=data.get("message", "Failed to retrieve user info"),
                    )

                return data.get("data", {})

            except httpx.RequestError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Unable to connect to Member Center: {exc}",
                )

member_center = MemberCenterClient()
