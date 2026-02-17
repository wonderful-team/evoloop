import logging
from typing import Optional, Any
from .store import IdentityStore
from .jwt import create_local_jwt

logger = logging.getLogger(__name__)


class IdentityService:
    """
    Unified Service for Identity and Token Management.
    Orchestrates interaction between Cloud Tokens, Local JWTs, and Persona/User data.
    """

    def __init__(self):
        self.store = IdentityStore()

    async def login_with_cloud_result(self, cloud_result: dict[str, Any]) -> Optional[str]:
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

        # 2. Issue Local JWT
        # We store member_id in the local JWT claims
        local_token = create_local_jwt({"sub": str(member_id), "member_id": member_id})
        return local_token

    def logout(self):
        """
        Clears all local auth state.
        """
        self.store.delete_cloud_token()
        # Note: We don't necessarily delete the device_key here as it identifies the device, not the user session.

    def get_cloud_token(self) -> Optional[str]:
        """
        Retrieves the cloud token from secure storage.
        """
        return self.store.get_cloud_token()

    def get_member_id(self) -> Optional[int]:
        return self.store.get_member_id()

    def is_logged_in(self) -> bool:
        return self.store.get_cloud_token() is not None


# Global instance
identity_service = IdentityService()
