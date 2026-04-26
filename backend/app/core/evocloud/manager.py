import logging
import time
from collections.abc import Callable
from typing import Any

from app.core.config import settings
from app.core.evocloud.backends.http_client import EvoCloudHTTPClient
from app.core.evocloud.backends.websocket_link import EvoCloudWebSocketLink
from app.core.evocloud.schemas import EvoCloudConfig
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.auth import LoginResult
from app.utils.async_utils import LoopBoundResource

logger = logging.getLogger(__name__)

# Conversation sync manager
_conversation_sync_manager = None


class EvoCloudProjectSummary(DynamicBaseModel):
    id: int | None = None
    name: str
    description: str = ""
    path: str = ""
    exists_locally: bool = False
    status_text: str = ""
    owner: str = ""


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
        self._link: EvoCloudWebSocketLink | None = None
        # Project cache with TTL
        self._projects_cache: list[EvoCloudProjectSummary] | None = None
        self._projects_cache_time: float = 0.0
        self._projects_cache_ttl: int = 60  # 60 seconds TTL
        self._projects_cache_lock = False  # Simple lock for cache refresh

    def initialize(self, config: EvoCloudConfig | None = None) -> None:
        """
        Initialize the manager with configuration.
        If config is not provided, tries to load from global settings (for transition).
        """
        if self._initialized:
            return

        if config is None:
            # Fallback to loading from global settings
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

        self._api_pool = LoopBoundResource(
            factory=lambda: EvoCloudHTTPClient(self._config),
            cleanup=cleanup_api
        )

        self._link = EvoCloudWebSocketLink(self._config, self._api_pool.get())
        if hasattr(self, '_query_handler') and self._query_handler:
            self._link.set_query_handler(self._query_handler)

        self._initialized = True
        logger.info("EvoCloudManager: Initialized")

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start background services (Link) for the current loop."""
        if self.link:
            await self.link.start()

        # Start conversation sync to MC
        await self._start_conversation_sync()

    async def stop(self) -> None:
        """Stop background services across all tracked loops."""
        # Stop conversation sync
        await self._stop_conversation_sync()

        if self._link:
            await self._link.stop()
        if self._api_pool:
            await self._api_pool.flush_all()

    async def _start_conversation_sync(self):
        """Start conversation history sync to Member Center"""
        global _conversation_sync_manager

        try:
            from app.core.evocloud.bridge.conversation_sync import ConversationSyncManager

            if _conversation_sync_manager is None:
                # Get device_key from link (it's generated in WebSocketLink)
                device_key = self.link.device_key if self.link else ""
                _conversation_sync_manager = ConversationSyncManager(
                    api_client=self.api,
                    device_key=device_key,
                )
                logger.info(f"[EvoCloud] ConversationSyncManager created with device_key={device_key}")

            await _conversation_sync_manager.start()
            logger.info("[EvoCloud] Conversation sync started")
        except Exception as e:
            logger.error(f"[EvoCloud] Failed to start conversation sync: {e}")

    async def _stop_conversation_sync(self):
        """Stop conversation history sync"""
        global _conversation_sync_manager

        if _conversation_sync_manager:
            try:
                await _conversation_sync_manager.stop()
                _conversation_sync_manager = None
                logger.info("[EvoCloud] Conversation sync stopped")
            except Exception as e:
                logger.error(f"[EvoCloud] Error stopping conversation sync: {e}")

    # --- Callbacks / Bridge ---

    def set_query_handler(self, handler: Callable[[str, str, dict[str, Any]], Any]):
        """设置查询处理器: (query_type, thread_id, params) -> result"""
        self._query_handler = handler
        if self._initialized and hasattr(self.link, 'set_query_handler'):
            self.link.set_query_handler(handler)

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
        if resp.get("code") != 0:
            logger.error(f"Failed to fetch projects from API: {resp.get('message')}")
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
        res = await self.api.login(username, password)
        if res.get("success") and self.link:
            # Token is auto-saved by API backend, but maybe we want to trigger link start here?
            # Existing login.py does that manually. Let's keep it manual or handle it here?
            # To be safe and compatible with existing flow, we primarily return result.
            # But we can also ensure token is updated in memory if needed.
            if res.get("token"):
                self.api.set_token(res.get("token"))
                await self.link.start()  # Auto start link on login
        return res

    def get_token(self) -> str | None:
        return self.api.get_token() if self._api_pool else None

    # --- Properties ---

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
        return self._link

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
