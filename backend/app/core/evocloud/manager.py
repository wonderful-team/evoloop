import logging
import time
from collections.abc import Callable
from typing import Any

from app.celery_app import celery_app
from app.core.config import settings
from app.core.context.manager import ContextManager
from app.core.evocloud.backends.http_client import EvoCloudHTTPClient
from app.core.evocloud.backends.websocket_link import EvoCloudWebSocketLink
from app.core.evocloud.schemas import EvoCloudConfig

logger = logging.getLogger(__name__)


from app.utils.async_utils import LoopBoundResource

class EvoCloudManager:
    """
    Unified Facade for EvoCloud Core Module.
    Manages API Client and WebSocket Link lifecycles using Loop-Bound mechanisms.
    """

    def __init__(self):
        self._initialized = False
        self._config: EvoCloudConfig | None = None
        self._api_pool: LoopBoundResource[EvoCloudHTTPClient] | None = None
        self._link_pool: LoopBoundResource[EvoCloudWebSocketLink] | None = None
        self._command_handler = None
        self._event_handler = None

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
                app_data_dir=str(settings.APP_DATA_DIR)
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
        
        def create_link():
            link = EvoCloudWebSocketLink(self._config, self.api)
            if self._command_handler:
                link.set_command_handler(self._command_handler)
            if self._event_handler:
                link.set_event_handler(self._event_handler)
            return link
            
        self._link_pool = LoopBoundResource(
            factory=create_link,
            cleanup=cleanup_link
        )

        self._initialized = True
        logger.info("EvoCloudManager: Initialized")

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start background services (Link) for the current loop."""
        if self.link:
            await self.link.start()

    async def stop(self) -> None:
        """Stop background services across all tracked loops."""
        if self._link_pool:
            await self._link_pool.flush_all()
        if self._api_pool:
            await self._api_pool.flush_all()

    # --- Callbacks / Bridge ---

    def set_command_handler(self, handler: Callable[[dict[str, Any]], None]):
        self._command_handler = handler
        if self._initialized:
            self.link.set_command_handler(handler)

    def set_event_handler(self, handler: Callable[[str, dict[str, Any]], None]):
        self._event_handler = handler
        if self._initialized:
            self.link.set_event_handler(handler)

    # --- Proxy Methods (Common Actions) ---

    # Auth
    async def login(self, username, password) -> dict:
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
        return self._link_pool.get()

    # Chat Sync (Agent.py support)
    async def upload_log(self, thread_id: str, log_type: str, content: Any, name: str | None = None, device_id: int | None = None, command_id=None, project_id=None, persistent: bool = True):
        if not self.api: return

        # Auto-fill from context if missing
        if not project_id or not command_id:
            ctx = ContextManager.current()
            project_id = project_id or ctx.project_id
            command_id = command_id or ctx.command_id

        # Auto-fill device_id if not provided
        target_device_id = device_id or self.device_id
        if not target_device_id:
            logger.debug("Skipping upload_log: No device_id available")
            return

        # Try WebSocket Streaming First (Real-time)
        if self.link and self.link.is_connected():
            # Construct payload matching Mobile App expectation
            payload = {
                "type": "log_streaming",  # Cloud will forward this as 'new_logs' or similar
                "data": {
                    "logs": [{
                        "type": log_type,
                        "name": name,
                        "content": content,
                        "thread_id": thread_id,
                        "project_id": project_id,
                        "timestamp": int(time.time() * 1000)
                    }],
                    "project_id": project_id
                }
            }
            await self.link.send_message(payload)

        # Persistent storage (DB) - Offloaded to Celery
        if persistent:
            try:
                celery_app.send_task(
                    "engine_upload_cloud_log",
                    kwargs={
                        "device_id": target_device_id,
                        "thread_id": thread_id,
                        "log_type": log_type,
                        "content": content,
                        "name": name,
                        "command_id": command_id,
                        "project_id": project_id
                    }
                )
                logger.debug(f"Dispatched cloud log persistence for {log_type} to Celery")
            except Exception as ex:
                logger.warning(f"Failed to dispatch cloud log to Celery: {ex}. Falling back to sync.")
                # Fallback to direct call if Celery fails
                await self.api.upload_log(target_device_id, thread_id, log_type, content, name=name, command_id=command_id, project_id=project_id)

    async def scan_projects(self) -> list[dict]:
        """Fetch projects from EvoCloud API."""
        import os
        try:
            resp = await self.api.get_projects(page=1, page_size=100)
            if resp.get("code") != 0:
                logger.error(f"Failed to fetch projects from API: {resp.get('message')}")
                return []

            api_projects = resp.get("data", {}).get("list", [])
            projects = []
            for p in api_projects:
                path = p.get("external_path", "")
                projects.append({
                    "id": p.get("project_id"),
                    "name": p.get("project_name", "Unknown"),
                    "description": p.get("project_desc", ""),
                    "path": path,
                    "exists_locally": os.path.exists(path) if path else False,
                    "status_text": p.get("status_text", ""),
                    "owner": p.get("owner_member_name", "")
                })
            return projects
        except Exception as e:
            logger.error(f"scan_projects failed: {e}")
            return []

    async def get_project_by_id(self, project_id: int) -> dict | None:
        """Get project details by numeric ID."""
        projects = await self.scan_projects()
        for p in projects:
            if p.get("id") == project_id:
                return p
        return None

    @property
    def device_id(self) -> int | None:
        return self.link.device_id if self.link else None


# Global Instance
evocloud_manager = EvoCloudManager()
