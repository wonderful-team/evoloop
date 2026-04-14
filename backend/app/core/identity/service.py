import logging
from typing import Any

from app.models.schemas.auth import LoginResult

from .jwt import create_local_jwt, decode_local_jwt, JwtPayload
from .store import IdentityStore

logger = logging.getLogger(__name__)


class IdentityService:
    """
    Unified Service for Identity and Token Management.
    Orchestrates interaction between Cloud Tokens, Local JWTs, and Persona/User data.
    """

    def __init__(self):
        self.store = IdentityStore()

    async def login_with_cloud_result(self, cloud_result: LoginResult) -> str | None:
        """
        Processes a successful login result from EvoCloud.
        Saves cloud token to secure storage and returns a local JWT.
        """
        token = cloud_result.get("token")
        member_id = cloud_result.get("member_id", 0)

        if not token:
            logger.error("Login result missing token")
            return None

        # 1. Save Cloud Token securely
        self.store.save_cloud_token(token)
        self.store.save_member_id(member_id)

    async def create_local_token_from_id(self, member_id: int, username: str = None) -> str:
        """
        Creates a thin local JWT from a member_id.
        No cloud interaction, just identity resolution.
        """
        claims = JwtPayload(sub=str(member_id), member_id=member_id)
        if username:
            claims.username = username
        return create_local_jwt(claims)

    def logout(self):
        """
        Clears all local auth state.
        """
        self.store.delete_cloud_token()
        # Note: We don't necessarily delete the device_key here as it identifies the device, not the user session.

    def get_cloud_token(self) -> str | None:
        """
        Retrieves the cloud token from secure storage.
        """
        return self.store.get_cloud_token()

    def get_member_id(self, token: str | None = None) -> int | None:
        if token:
            payload = decode_local_jwt(token)
            return payload.get("member_id") if payload else None
        return self.store.get_member_id()

    def is_logged_in(self) -> bool:
        return self.store.get_cloud_token() is not None


# Global instance
identity_service = IdentityService()
