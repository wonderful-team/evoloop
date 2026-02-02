import asyncio
import json
import logging
import os
import time
from typing import Any

import httpx

from app.core.evocloud.interfaces.client import EvoCloudClientProtocol
from app.core.evocloud.schemas import EvoCloudConfig
from app.utils import file as file_utils
from app.utils import http as http_utils
from app.utils import json as json_utils
from app.utils.security import generate_hmac_signature

logger = logging.getLogger(__name__)


class EvoCloudHTTPClient(EvoCloudClientProtocol):
    """
    Standardized HTTP Client for EvoCloud.
    """

    def __init__(self, config: EvoCloudConfig):
        self.config = config
        self.base_url = str(config.api_url).rstrip("/")
        self.timeout = 30.0

        self._user_token: str | None = config.access_token
        self._member_id: int | None = None
        self._clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}

        self._load_token()

    async def get_client(self) -> httpx.AsyncClient:
        """Get httpx client bound to current event loop"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return http_utils.create_client(timeout=self.timeout)

        if loop in self._clients:
            client = self._clients[loop]
            if not client.is_closed:
                return client

        # Create new
        client = http_utils.create_client(timeout=self.timeout)
        self._clients[loop] = client
        return client

    async def close(self):
        for client in self._clients.values():
            if not client.is_closed:
                await client.aclose()
        self._clients.clear()

    # --- Auth Helpers ---

    def set_token(self, token: str | None) -> None:
        self._user_token = token
    
    def get_token(self) -> str | None:
        return self._user_token

    def get_member_id(self) -> int | None:
        return self._member_id

    def _load_token(self):
        try:
            if self._user_token:
                return

            # Keep compatibility with existing auth file
            auth_file = os.path.join(os.getcwd(), ".evoloop", "auth.json")
            if os.path.exists(auth_file):
                content = file_utils.read_file(auth_file)
                data = json_utils.loads(content)
                self._user_token = data.get("token")
                self._member_id = data.get("member_id")
        except Exception as e:
            logger.warning(f"Failed to load auth token: {e}")

    def _save_token(self, token: str, member_id: int):
        try:
            self._user_token = token
            self._member_id = member_id

            auth_dir = os.path.join(os.getcwd(), ".evoloop")
            os.makedirs(auth_dir, exist_ok=True)

            with open(os.path.join(auth_dir, "auth.json"), "w") as f:
                json.dump({"token": token, "member_id": member_id}, f)
        except Exception as e:
            logger.error(f"Failed to save auth token: {e}")

    def logout(self):
        self._user_token = None
        self._member_id = None
        try:
            auth_file = os.path.join(os.getcwd(), ".evoloop", "auth.json")
            if os.path.exists(auth_file):
                os.remove(auth_file)
        except Exception:
            pass

    # --- Request Core ---

    def _generate_signature(self, method: str, uri: str, body: str, timestamp: int) -> str:
        if not self.config.api_secret:
            return ""
        string_to_sign = f"{method}\\n{uri}\\n{body}\\n{timestamp}"
        return generate_hmac_signature(self.config.api_secret, string_to_sign)

    async def request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        data: dict | None = None,
        token: str | None = None,
        headers: dict | None = None
    ) -> dict:
        client = await self.get_client()
        active_token = token or self._user_token

        url = f"{self.base_url}{endpoint}"
        timestamp = int(time.time())
        body_str = json_utils.dumps(data) if data else ""

        req_headers = headers or {}
        req_headers.update({
            "Content-Type": "application/json", 
            "X-Timestamp": str(timestamp)
        })

        if self.config.api_key and self.config.api_secret:
            req_headers["X-API-Key"] = self.config.api_key
            req_headers["X-Signature"] = self._generate_signature(method, endpoint, body_str, timestamp)

        if params is None:
            params = {}
        if active_token:
            params["token"] = active_token

        try:
            logger.debug(f"Req: {method} {endpoint}")
            resp = await client.request(method, url, params=params, json=data, headers=req_headers)

            if resp.status_code >= 400:
                logger.error(f"API Error {resp.status_code}: {resp.text[:200]}")

            try:
                res_json = resp.json()
                return res_json
            except json.JSONDecodeError:
                return {"code": -1, "message": f"Invalid JSON: {resp.text[:100]}"}

        except httpx.RequestError as e:
            logger.error(f"Request connection error: {e}")
            return {"code": -1, "message": str(e)}
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return {"code": -1, "message": str(e)}

    # --- Business Methods ---

    async def login(self, username, password) -> dict:
        res = await self.request("POST", "/api/login/login", data={"username": username, "password": password})
        if res.get("code", -1) >= 0:
            token = res.get("data", {}).get("token")
            if token:
                self._save_token(token, 0)  # member_id 0 or unknown initially
                return {"success": True, "token": token}
        return {"success": False, "message": res.get("message", "Login failed")}

    async def get_user_info(self, token: str | None = None) -> dict:
        return await self.request("GET", "/api/member/info", token=token)

    # Project
    async def get_projects(self, page=1, page_size=100) -> dict:
        return await self.request(
            "GET",
            "/projectmanage/api/projectOpen/projects",
            params={"page": page, "page_size": page_size},
        )

    async def create_project(self, name: str, description: str, path: str) -> dict:
        payload = {
            "name": name,
            "description": description,
            "path": path,
            "source": "EvoLoop",
        }
        return await self.request("POST", "/projectmanage/api/projectOpen/createProject", data=payload)

    async def update_project(
        self,
        project_id: int,
        description: str = None,
        name: str = None,
        path: str = None,
    ) -> dict:
        data = {"project_id": project_id}
        if description is not None:
            data["project_desc"] = description
        if name is not None:
            data["name"] = name
        if path is not None:
            data["path"] = path
        return await self.request("POST", "/projectmanage/api/projectOpen/updateProject", data=data)

    async def delete_project(self, project_id: int) -> dict:
        return await self.request(
            "POST",
            "/projectmanage/api/projectOpen/deleteProject",
            data={"project_id": project_id},
        )

    async def get_current_project(self, token: str | None = None) -> dict:
        return await self.request("GET", "/projectmanage/api/projectOpen/getCurrentProject", token=token)

    # Task
    async def get_project_tasks(self, project_id: int, page=1, page_size=50, status=None, token=None) -> dict:
        p = {"project_id": project_id, "page": page, "page_size": page_size}
        if status is not None:
            p["status"] = status
        return await self.request("GET", "/projectmanage/api/task/projectTasks", params=p, token=token)

    async def get_task_detail(self, task_id: int, token=None) -> dict:
        return await self.request("GET", f"/projectmanage/api/task/detail/{task_id}", token=token)

    async def create_task(self, data: dict, token=None) -> dict:
        return await self.request("POST", "/projectmanage/api/task/create", data=data, token=token)

    async def update_task(self, task_id: int, data: dict, token=None) -> dict:
        return await self.request("PUT", f"/projectmanage/api/task/update/{task_id}", data=data, token=token)

    async def delete_task(self, task_id: int, token=None) -> dict:
        return await self.request(
            "DELETE",
            "/projectmanage/api/task/delete",
            data={"task_id": task_id},
            token=token,
        )

    async def update_task_status(self, task_id: int, status: int, progress: int = 0, token=None) -> dict:
        return await self.request(
            "POST",
            "/projectmanage/api/task/updateStatus",
            data={"task_id": task_id, "status": status, "progress": progress},
            token=token,
        )

    # Modules
    async def get_budget_list(self, project_id: int, page=1, page_size=50, token=None) -> dict:
        return await self.request(
            "GET",
            "/projectmanage/api/budget/lists",
            params={"project_id": project_id, "page": page, "page_size": page_size},
            token=token,
        )

    async def get_budget_overview(self, project_id: int, token=None) -> dict:
        return await self.request(
            "GET",
            "/projectmanage/api/budget/overview",
            params={"project_id": project_id},
            token=token,
        )

    async def get_timesheet_list(self, project_id: int, page=1, page_size=50, token=None) -> dict:
        return await self.request(
            "GET",
            "/projectmanage/api/timesheet/lists",
            params={"project_id": project_id, "page": page, "page_size": page_size},
            token=token,
        )

    async def add_timesheet_quick(self, data: dict, token=None) -> dict:
        return await self.request("POST", "/projectmanage/api/timesheet/quickAdd", data=data, token=token)

    async def get_project_statistics(self, project_id=0, token=None) -> dict:
        p = {"project_id": project_id} if project_id else {}
        return await self.request("GET", "/projectmanage/api/project/statistics", params=p, token=token)

    async def get_ai_global_config(self) -> dict:
        return await self.request("GET", "/api/AI/globalConfig")

    # Cancellation
    async def get_cancellation_info(self) -> dict:
        return await self.request("GET", "/membercancel/api/membercancel/info")

    async def apply_cancellation(self) -> dict:
        return await self.request("POST", "/membercancel/api/membercancel/apply")

    async def cancel_cancellation_apply(self) -> dict:
        return await self.request("POST", "/membercancel/api/membercancel/cancelApply")

    # Public / Auth
    async def get_captcha_config(self) -> dict:
        return await self.request("GET", "/api/captcha/config")

    async def get_captcha(self, captcha_id: str) -> dict:
        return await self.request("GET", "/api/captcha/get", params={"id": captcha_id})

    async def get_register_config(self) -> dict:
        return await self.request("GET", "/api/register/config")

    async def get_register_agreement(self) -> dict:
        return await self.request("GET", "/api/register/agreement")

    async def send_mobile_code(self, mobile: str, captcha_id: str, captcha_code: str, type: str = "login") -> dict:
        return await self.request(
            "POST",
            "/api/sms/send",
            data={
                "mobile": mobile,
                "captcha_id": captcha_id,
                "captcha_code": captcha_code,
                "type": type,
            },
        )

    async def register_mobile(self, data: dict) -> dict:
        return await self.request("POST", "/api/register/mobile", data=data)

    async def register_username(self, data: dict) -> dict:
        return await self.request("POST", "/api/register/account", data=data)

    async def login_mobile(self, mobile: str, key: str, code: str) -> dict:
        res = await self.request(
            "POST",
            "/passport/api/login/mobile",
            data={"mobile": mobile, "key": key, "code": code},
        )
        if res.get("code", -1) >= 0:
            token = res.get("data", {}).get("token")
            if token:
                self._save_token(token, 0)
                return {
                    "success": True,
                    "token": token,
                    "member_id": res.get("data", {}).get("member_id"),
                }
        return {"success": False, "message": res.get("message", "Login failed")}

    async def check_mobile_exist(self, mobile: str) -> dict[str, Any]:
        return await self.request("GET", "/passport/api/mobile/check", params={"mobile": mobile})

    async def reset_password_by_mobile(self, mobile: str, code: str, key: str, password: str) -> dict[str, Any]:
        return await self.request(
            "POST",
            "/passport/api/password/reset/mobile",
            data={"mobile": mobile, "code": code, "key": key, "password": password},
        )

    # Device Specific via API
    async def get_devices(self, token: str | None = None) -> dict:
        return await self.request("GET", "/evolooplink/api/device/list", token=token)

    async def send_command_to_device(self, device_id: int, cmd_data: dict, token: str | None = None) -> dict:
        data = {"device_id": device_id, **cmd_data}
        return await self.request("POST", "/evolooplink/api/command/send", data=data, token=token)

    async def get_device_logs(self, device_id: int, limit=20, project_id=None, token: str | None = None) -> dict:
        params = {"device_id": device_id, "limit": limit}
        if project_id:
            params["project_id"] = project_id
        return await self.request("GET", "/evolooplink/api/log/recent", params=params, token=token)

    async def search_device_logs(self, device_id: int, query: str, limit=20, project_id=None, token: str | None = None) -> dict:
        params = {"device_id": device_id, "query": query, "limit": limit}
        if project_id:
            params["project_id"] = project_id
        return await self.request("GET", "/evolooplink/api/log/search", params=params, token=token)

    async def register_device(self, key: str, name: str, os_info: str) -> dict:
        """Raw API call to register device."""
        return await self.request(
            "POST",
            "/evolooplink/api/device/register",
            data={
                "device_key": key,
                "device_name": name,
                "device_type": "desktop",
                "os_info": os_info,
            },
        )

    async def send_heartbeat(self, device_id: int):
        await self.request("POST", "/evolooplink/api/device/heartbeat", data={"device_id": device_id})

    async def bind_client_id(self, device_id: int, client_id: str):
        await self.request(
            "POST",
            "/evolooplink/api/device/bind",
            data={"device_id": device_id, "client_id": client_id},
        )

    async def update_command_status(self, command_id, status, result=None):
        data = {"command_id": command_id, "status": status}
        if result:
            data["result"] = result
        await self.request("POST", "/evolooplink/api/command/updateStatus", data=data)

    async def upload_log(self, device_id, thread_id, log_type, content, command_id=None, project_id=None):
        data = {
            "device_id": device_id,
            "thread_id": thread_id,
            "type": log_type,
            "content": json_utils.dumps(content) if isinstance(content, dict | list) else str(content),
        }
        if command_id:
            data["command_id"] = command_id
        if project_id:
            data["project_id"] = project_id
        await self.request("POST", "/evolooplink/api/log/upload", data=data)
