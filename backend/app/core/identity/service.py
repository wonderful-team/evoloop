import logging
import time

from app.core.config import settings
from app.models.schemas.auth import LoginResult
from .store import IdentityStore
from app.infrastructure.cache import cache

logger = logging.getLogger(__name__)

# Token -> (member_id, timestamp) 本地缓存
TOKEN_CACHE_TTL = 120  # 2 minutes
MAX_CACHE_SIZE = 1000  # 防止内存泄漏


class IdentityService:
    """
    Unified Service for Identity and Token Management.
    Uses access tokens (issued by Member Center) as the single source of truth.
    """

    def __init__(self):
        self.store = IdentityStore()

    async def login_with_cloud_result(self, cloud_result: LoginResult) -> None:
        """
        Processes a successful login result from EvoCloud.
        Saves access token and member_id to cache-backed storage.
        """
        token = cloud_result.get("token")
        refresh_token = cloud_result.get("refresh_token")
        if not refresh_token:
            data = cloud_result.get("data") or {}
            refresh_token = data.get("refresh_token")
        member_id = cloud_result.get("member_id", 0)

        if not token:
            logger.error("Login result missing token")
            return

        await self.set_token(token, refresh_token)
        if member_id:
            await self.store.save_member_id(member_id)

    async def set_token(self, token: str, refresh_token: str | None = None) -> None:
        """Updates the stored access token and optionally the refresh token."""
        await self.store.save_access_token(token)
        if refresh_token:
            await self.store.save_refresh_token(refresh_token)

        # Notify subscribers if any (like WebSocket link)
        if hasattr(self, "_on_token_change_cb") and self._on_token_change_cb:
            self._on_token_change_cb(token)

    def on_token_change(self, callback):
        self._on_token_change_cb = callback

    async def logout(self):
        """Clears all local auth state."""
        token = await self.store.get_access_token()
        await self.store.clear()
        if token:
            await cache.delete(f"evoloop:token_mid:{token}")

    async def get_access_token(self) -> str | None:
        """Retrieves the access token from cache-backed storage."""
        if settings.MULTI_TENANT_MODE:
            return None
        return await self.store.get_access_token()

    async def get_refresh_token(self) -> str | None:
        """Retrieves the refresh token from cache-backed storage."""
        if settings.MULTI_TENANT_MODE:
            return None
        return await self.store.get_refresh_token()

    async def resolve_member_id_from_token(self, token: str) -> int | None:
        """
        Resolve member_id from an access token with local caching.
        Falls back to Member Center API if not cached.
        """
        # 1. Check shared cache
        cache_key = f"evoloop:token_mid:{token}"
        cached_mid_str = await cache.get(cache_key)
        if cached_mid_str:
            return int(cached_mid_str)

        # 2. Validate against Member Center
        try:
            from app.core.evocloud import evocloud_manager
            result = await evocloud_manager.api.get_user_info(token)
            if result.get("code") == 0:
                data = result.get("data", {})
                member_id = data.get("member_id")
                if member_id is not None:
                    mid = int(member_id)
                    await cache.set(cache_key, str(mid), ex=TOKEN_CACHE_TTL)

                    # Sync to store only if user changed (e.g. login on another device/client)
                    # or if the store is currently empty.
                    # Sync to store only if user changed AND we are in single-user mode
                    if not settings.MULTI_TENANT_MODE:
                        stored_mid = await self.store.get_member_id()
                        if stored_mid is None or stored_mid != mid:
                            logger.info(f"[Identity] Syncing session to store for new/different user (mid: {mid})")
                            await self.store.save_access_token(token)
                            await self.store.save_member_id(mid)
                    return mid
        except Exception as e:
            logger.error(f"Failed to resolve member_id from token: {e}")

        return None

    async def get_member_id(self, token: str | None = None) -> int | None:
        """
        Get member_id. If token is provided, resolves from token (with caching).
        Otherwise returns the stored member_id for the current session.
        """
        if token:
            return await self.resolve_member_id_from_token(token)

        if settings.MULTI_TENANT_MODE:
            return None

        return await self.store.get_member_id()

    async def is_logged_in(self) -> bool:
        return await self.store.get_access_token() is not None


# Global instance
identity_service = IdentityService()
