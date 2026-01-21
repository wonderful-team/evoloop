import asyncio
import logging
from collections.abc import Callable

import httpx

from app.infrastructure.external.evocloud.api import EvoCloudAPI
from app.infrastructure.external.evocloud.device_link import DeviceLinkManager

logger = logging.getLogger(__name__)


class EvoCloudClient:
    """
    Unified Client Facade via EvoCloudAPI and DeviceLinkManager.
    Maintains backward compatibility.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.api = EvoCloudAPI()
        self.link = DeviceLinkManager(self.api)

        self._initialized = True
        logger.info("EvoCloudClient Facade Initialized")

    # --- Properties (Compat) ---
    @property
    def device_id(self):
        return self.link.device_id

    @property
    def device_name(self):
        return self.link.device_name

    @property
    def _user_token(self):
        return self.api.get_token()

    # --- Methods Delegated to API ---
    async def get_client(self) -> httpx.AsyncClient:
        return await self.api.get_client()

    async def close(self):
        await self.api.close()
        await self.link.stop()

    async def logout(self):
        await self.link.stop()
        self.api.logout()

    def get_status(self):
        return {
            "is_logged_in": bool(self.api.get_token()),
            "member_id": self.api.get_member_id(),
            "device_connected": self.link.is_connected(),
            "device_id": self.link.device_id,
        }

    async def login(self, username, password) -> dict:
        res = await self.api.login(username, password)
        if res.get("success"):
            # Auto start link like before
            asyncio.create_task(self.link.start())
        return res

    async def get_user_info(self, token=None):
        return await self.api.get_user_info(token)

    async def get_projects(self, page=1, page_size=100) -> dict:
        return await self.api.get_projects(page, page_size)

    async def create_project(self, name, description, path) -> dict:
        return await self.api.create_project(name, description, path)

    async def update_project(self, project_id, description=None, name=None, path=None) -> dict:
        return await self.api.update_project(project_id, description, name, path)

    async def delete_project(self, project_id) -> dict:
        return await self.api.delete_project(project_id)

    async def get_current_project(self, token=None):
        return await self.api.get_current_project(token)

    async def get_project_tasks(self, project_id, page=1, page_size=50, status=None, token=None) -> dict:
        return await self.api.get_project_tasks(project_id, page, page_size, status, token)

    async def get_task_detail(self, task_id, token=None) -> dict:
        return await self.api.get_task_detail(task_id, token)

    async def create_task(self, data, token=None) -> dict:
        return await self.api.create_task(data, token)

    async def update_task(self, task_id, data, token=None) -> dict:
        return await self.api.update_task(task_id, data, token)

    async def delete_task(self, task_id, token=None) -> dict:
        return await self.api.delete_task(task_id, token)

    async def update_task_status(self, task_id, status, progress=0, token=None) -> dict:
        return await self.api.update_task_status(task_id, status, progress, token)

    async def get_budget_list(self, project_id, page=1, page_size=50, token=None) -> dict:
        return await self.api.get_budget_list(project_id, page, page_size, token)

    async def get_budget_overview(self, project_id, token=None) -> dict:
        return await self.api.get_budget_overview(project_id, token)

    async def get_timesheet_list(self, project_id, page=1, page_size=50, token=None) -> dict:
        return await self.api.get_timesheet_list(project_id, page, page_size, token)

    async def add_timesheet_quick(self, data, token=None) -> dict:
        return await self.api.add_timesheet_quick(data, token)

    async def get_project_statistics(self, project_id=0, token=None) -> dict:
        return await self.api.get_project_statistics(project_id, token)

    async def get_ai_global_config(self) -> dict:
        return await self.api.get_ai_global_config()

    async def get_cancellation_info(self) -> dict:
        return await self.api.get_cancellation_info()

    async def apply_cancellation(self) -> dict:
        return await self.api.apply_cancellation()

    async def cancel_cancellation_apply(self) -> dict:
        return await self.api.cancel_cancellation_apply()

    async def get_captcha_config(self) -> dict:
        return await self.api.get_captcha_config()

    async def get_captcha(self, captcha_id) -> dict:
        return await self.api.get_captcha(captcha_id)

    async def get_register_config(self) -> dict:
        return await self.api.get_register_config()

    async def get_register_agreement(self) -> dict:
        return await self.api.get_register_agreement()

    async def send_mobile_code(self, mobile, captcha_id, captcha_code, type="login") -> dict:
        return await self.api.send_mobile_code(mobile, captcha_id, captcha_code, type)

    async def register_mobile(self, data) -> dict:
        return await self.api.register_mobile(data)

    async def register_username(self, data) -> dict:
        return await self.api.register_username(data)

    async def login_mobile(self, mobile, key, code) -> dict:
        res = await self.api.login_mobile(mobile, key, code)
        if res.get("success"):
            asyncio.create_task(self.link.start())
        return res

    async def check_mobile_exist(self, mobile) -> dict:
        return await self.api.check_mobile_exist(mobile)

    async def reset_password_by_mobile(self, mobile, code, key, password) -> dict:
        return await self.api.reset_password_by_mobile(mobile, code, key, password)

    async def get_devices(self) -> dict:
        return await self.api.get_devices()

    async def send_command_to_device(self, device_id, cmd_data) -> dict:
        return await self.api.send_command_to_device(device_id, cmd_data)

    async def get_device_logs(self, device_id, limit=20, project_id=None) -> dict:
        return await self.api.get_device_logs(device_id, limit, project_id)

    async def search_device_logs(self, device_id, query, limit=20, project_id=None) -> dict:
        return await self.api.search_device_logs(device_id, query, limit, project_id)

    async def upload_log(self, thread_id, log_type, content, command_id=None, project_id=None):
        # Requires device_id from Link
        if not self.link.device_id:
            return
        await self.api.upload_log(self.link.device_id, thread_id, log_type, content, command_id, project_id)

    # --- Methods Delegated to DeviceLink ---
    def set_command_handler(self, handler: Callable):
        self.link.set_command_handler(handler)

    def set_event_handler(self, handler: Callable):
        self.link.set_event_handler(handler)

    async def start_device_link(self, token: str | None = None):
        if token:
            # Updating token in API, Link reads from API
            self.api._save_token(token, 0)
        await self.link.start()

    async def stop_device_link(self):
        await self.link.stop()


# Global Instance
evocloud_client = EvoCloudClient()
