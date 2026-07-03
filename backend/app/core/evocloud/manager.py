import logging
import time

from app.core.config import settings
from app.core.context import ContextManager
from app.core.evocloud.backends.http_client import EvoCloudHTTPClient
from app.core.evocloud.backends.websocket_link import EvoCloudWebSocketLink
from app.core.evocloud.schemas import EvoCloudConfig, EvoCloudProjectSummary
from app.models.schemas.auth import LoginResult
from app.utils.async_utils import LoopBoundResource

logger = logging.getLogger(__name__)


class EvoCloudManager:
    """
    Unified Facade for EvoCloud Core Module.
    Manages API Client and WebSocket Link lifecycles using Loop-Bound mechanisms.

    Optimizations:
    - Project list caching with TTL to reduce API calls
    - Async background refresh for cache warming
    """

    def __init__(self):
        self._initialized = False
        self._config: EvoCloudConfig | None = None
        self._api_pool: LoopBoundResource[EvoCloudHTTPClient] | None = None
        self._link_pool: LoopBoundResource[EvoCloudWebSocketLink] | None = None
        # Project cache with TTL
        self._projects_cache: list[EvoCloudProjectSummary] | None = None
        self._projects_cache_time: float = 0.0
        self._projects_cache_ttl: int = 60  # 60 seconds TTL
        self._projects_cache_lock = False  # Simple lock for cache refresh
        self._init_lock = False  # Simple lock for thread-safe initialization

    def initialize(self, config: EvoCloudConfig | None = None) -> None:
        """
        Initialize the manager with configuration.
        If config is not provided, tries to load from global settings (for transition).
        """
        if self._initialized:
            return

        self._init_lock = True

        try:
            if config is None:
                from app.core.config import settings
                config = EvoCloudConfig(
                    api_url=str(settings.EVOCLOUD_API_URL),
                    ws_url=str(settings.EVOCLOUD_WS_URL),
                    api_key=settings.EVOCLOUD_API_KEY,
                    api_secret=settings.EVOCLOUD_API_SECRET,
                    device_name=settings.EVOCLOUD_DEVICE_NAME,
                    access_token=settings.EVOCLOUD_ACCESS_TOKEN,
                    app_data_dir=str(settings.APP_DATA_DIR),
                    ssl_verify=getattr(settings, 'EVOCLOUD_SSL_VERIFY', True)
                )

            self._config = config

            async def cleanup_api(api):
                await api.close()

            async def cleanup_link(link):
                await link.stop()

            self._api_pool = LoopBoundResource(
                factory=lambda: EvoCloudHTTPClient(self._config),
                cleanup=cleanup_api
            )

            # Link is now also loop-bound to prevent cross-loop contamination
            def link_factory():
                return EvoCloudWebSocketLink(self._config, self.api)

            self._link_pool = LoopBoundResource(
                factory=link_factory,
                cleanup=cleanup_link
            )

            self._initialized = True
            logger.info("EvoCloudManager: Initialized with loop-bound resources")
        finally:
            self._init_lock = False

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start background services (Link) for the current loop."""
        if not settings.MOBILE_SYNC_ENABLED:
            logger.info("[EvoCloud] MOBILE_SYNC_ENABLED=false — skipping WebSocket link and conversation sync")
            return

        link = self.link
        if link:
            await link.start()

        # Start conversation sync to MC
        await self._start_conversation_sync()

    async def stop(self) -> None:
        """Stop background services across all tracked loops."""
        # Stop conversation sync
        await self._stop_conversation_sync()

        # Flush all loop-bound resources (triggers cleanup for both API and Link)
        if self._link_pool:
            await self._link_pool.flush_all()
        if self._api_pool:
            await self._api_pool.flush_all()

    async def _start_conversation_sync(self):
        """Start conversation history sync to Member Center"""
        try:
            from app.core.evocloud.bridge.conversation_sync import (
                start_conversation_sync,
            )

            # Get device_key from link (it's generated in WebSocketLink)
            device_key = self.link.device_key if self.link else ""
            await start_conversation_sync(
                api_client=self.api,
                device_key=device_key,
            )
            logger.info("[EvoCloud] Conversation sync started via bridge")
        except Exception as e:
            logger.error(f"[EvoCloud] Failed to start conversation sync: {e}")

    async def _stop_conversation_sync(self):
        """Stop conversation history sync"""
        try:
            from app.core.evocloud.bridge.conversation_sync import (
                stop_conversation_sync,
            )
            await stop_conversation_sync()
            logger.info("[EvoCloud] Conversation sync stopped via bridge")
        except Exception as e:
            logger.error(f"[EvoCloud] Error stopping conversation sync: {e}")

    # --- Cache Management ---

    def invalidate_projects_cache(self) -> None:
        """Invalidate the projects cache. Call this when projects are modified."""
        self._projects_cache = None
        self._projects_cache_time = 0.0
        logger.debug("[EvoCloud] Projects cache invalidated")

    async def _fetch_projects_from_api(self) -> list[EvoCloudProjectSummary]:
        """Internal method to fetch projects from API."""
        import os
        resp = await self.api.get_projects(page=1, page_size=100)
        if not resp or resp.get("code") != 0:
            logger.error(f"Failed to fetch projects from API: {resp.get('message') if resp else 'Empty response'}")
            return []

        api_projects = resp.get("data", {}).get("list", [])
        projects: list[EvoCloudProjectSummary] = []
        for p in api_projects:
            path = p.get("external_path", "")
            projects.append(EvoCloudProjectSummary(
                id=p.get("project_id"),
                name=p.get("project_name", "Unknown"),
                description=p.get("project_desc", ""),
                path=path,
                exists_locally=os.path.exists(path) if path else False,
                status_text=p.get("status_text", ""),
                owner=p.get("owner_member_name", "")
            ))
        return projects

    # --- Proxy Methods (Common Actions) ---

    # Auth
    async def login(self, username, password) -> LoginResult:
        """Login to Member Center. Token storage and service startup are handled by event subscribers."""
        res = await self.api.login(username, password)
        if res.get("success") and res.get("token"):
            await self.api.set_token(res.get("token"))
        return res

    async def get_token(self) -> str | None:
        # 1. 在多租户模式下，严格要求 Token 必须存在于请求上下文中，拒绝全局兜底
        if settings.MULTI_TENANT_MODE:
            return ContextManager.get_var("token")

        # 2. 在单租户（桌面端/单机版）模式下，允许兜底到全局缓存的 Token
        ctx_token = ContextManager.get_var("token")
        if ctx_token:
            return ctx_token

        return await self.api.get_token() if self._api_pool else None

    @property
    def config(self) -> EvoCloudConfig:
        if not self._initialized:
            self.initialize()
        return self._config

    @property
    def api(self) -> EvoCloudHTTPClient:
        if not self._initialized:
            self.initialize()
        return self._api_pool.get()

    @property
    def link(self) -> EvoCloudWebSocketLink:
        if not self._initialized:
            self.initialize()
        return self._link_pool.get()

    @property
    def sync_manager(self):
        """Access the global conversation sync manager."""
        from app.core.evocloud.bridge.conversation_sync import (
            _conversation_sync_manager,
        )
        return _conversation_sync_manager

    async def scan_projects(self) -> list[EvoCloudProjectSummary]:
        """
        Fetch projects from EvoCloud API with caching.

        Uses a 60-second TTL cache to avoid repeated API calls.
        Cache is invalidated when projects are modified.
        """
        now = time.time()

        # Check if cache is valid
        if (self._projects_cache is not None and
            (now - self._projects_cache_time) < self._projects_cache_ttl):
            logger.debug(f"[EvoCloud] Using cached projects ({len(self._projects_cache)} items, "
                        f"age: {now - self._projects_cache_time:.1f}s)")
            return list(self._projects_cache)  # Return copy to prevent mutation

        # Fetch fresh data
        try:
            start_time = time.time()
            projects = await self._fetch_projects_from_api()
            fetch_time = (time.time() - start_time) * 1000

            # Update cache
            self._projects_cache = projects
            self._projects_cache_time = time.time()

            logger.info(f"[EvoCloud] Fetched {len(projects)} projects from API in {fetch_time:.1f}ms")
            return list(projects)

        except Exception as e:
            logger.error(f"scan_projects failed: {e}")
            # Return stale cache if available, otherwise empty list
            if self._projects_cache is not None:
                logger.warning("[EvoCloud] Returning stale cache due to API error")
                return list(self._projects_cache)
            return []

    async def get_project_by_id(self, project_id: int) -> EvoCloudProjectSummary | None:
        """Get project details by numeric ID using cached data."""
        projects = await self.scan_projects()
        for p in projects:
            if p.get("id") == project_id:
                return p
        return None


# Global Instance
evocloud_manager = EvoCloudManager()
