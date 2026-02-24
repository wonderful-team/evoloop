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


class EvoCloudManager:
    """
    Unified Facade for EvoCloud Core Module.
    Manages API Client and WebSocket Link lifecycles.
    """

    def __init__(self):
        self._initialized = False
        self._config: EvoCloudConfig | None = None
        self._api: EvoCloudHTTPClient | None = None
        self.link: EvoCloudWebSocketLink | None = None

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
        self._api = EvoCloudHTTPClient(config)
        self.link = EvoCloudWebSocketLink(config, self._api)

        self._initialized = True
        logger.info("EvoCloudManager: Initialized")

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start background services (Link)."""
        if self.link:
            await self.link.start()

    async def stop(self) -> None:
        """Stop background services."""
        if self.link:
            await self.link.stop()
        if self._api:
            await self._api.close()

    # --- Callbacks / Bridge ---

    def set_command_handler(self, handler: Callable[[dict[str, Any]], None]):
        if self.link:
            self.link.set_command_handler(handler)
        else:
            logger.warning("Attempted to set command handler before initialization")

    def set_event_handler(self, handler: Callable[[str, dict[str, Any]], None]):
        if self.link:
            self.link.set_event_handler(handler)
        else:
            logger.warning("Attempted to set event handler before initialization")

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
                self._api.set_token(res.get("token"))
                await self.link.start() # Auto start link on login
        return res

    def get_token(self) -> str | None:
        return self._api.get_token() if self._api else None

    # --- Properties ---

    @property
    def config(self) -> EvoCloudConfig:
        if not self._config:
            self.initialize()
        return self._config

    @property
    def api(self) -> EvoCloudHTTPClient:
        if not self._api:
            self.initialize()
        return self._api

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
