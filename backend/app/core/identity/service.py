import logging
import time

from app.models.schemas.auth import LoginResult
from .store import IdentityStore

logger = logging.getLogger(__name__)

# Token -> (member_id, timestamp) 本地缓存
_token_member_cache: dict[str, tuple[int, float]] = {}
TOKEN_CACHE_TTL = 300  # 5 minutes
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
        await self.store.clear()
        _token_member_cache.clear()

    async def get_access_token(self) -> str | None:
        """Retrieves the access token from cache-backed storage."""
        return await self.store.get_access_token()

    async def get_refresh_token(self) -> str | None:
        """Retrieves the refresh token from cache-backed storage."""
        return await self.store.get_refresh_token()

    async def resolve_member_id_from_token(self, token: str) -> int | None:
        """
        Resolve member_id from an access token with local caching.
        Falls back to Member Center API if not cached.
        """
        # 1. Check local cache
        cached = _token_member_cache.get(token)
        if cached:
            member_id, ts = cached
            if time.time() - ts < TOKEN_CACHE_TTL:
                return member_id

        # 2. Validate against Member Center
        try:
            from app.core.evocloud import evocloud_manager
            result = await evocloud_manager.api.get_user_info(token)
            if result.get("code") == 0:
                data = result.get("data", {})
                member_id = data.get("member_id")
                if member_id is not None:
                    mid = int(member_id)
                    _token_member_cache[token] = (mid, time.time())

                    # 缓存清理：超出上限时移除最旧的 50%
                    if len(_token_member_cache) > MAX_CACHE_SIZE:
                        sorted_items = sorted(
                            _token_member_cache.items(), key=lambda x: x[1][1]
                        )
                        for i in range(len(sorted_items) // 2):
                            del _token_member_cache[sorted_items[i][0]]

                    # Sync to store only if token changed (avoid redundant writes)
                    stored_token = await self.store.get_access_token()
                    if stored_token != token:
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
        return await self.store.get_member_id()

    async def is_logged_in(self) -> bool:
        return await self.store.get_access_token() is not None


# Global instance
identity_service = IdentityService()
