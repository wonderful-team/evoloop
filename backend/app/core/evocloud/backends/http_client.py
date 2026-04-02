import asyncio
import json
import logging
import time
from typing import Any

import httpx

from app.core.evocloud.interfaces.client import EvoCloudClientProtocol
from app.core.evocloud.schemas import EvoCloudConfig
from app.core.identity import identity_service
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

        self._client: httpx.AsyncClient | None = None

        # Log Batching
        self._log_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._flush_task: asyncio.Task | None = None

    @property
    def root_url(self) -> str:
        url = self.base_url.rstrip("/")
        if url.endswith("/gateway"):
            return url[:-len("/gateway")]
        elif url.endswith("/member"):
            return url[:-len("/member")]
        return url

    async def get_client(self) -> httpx.AsyncClient:
        """Get httpx client bound to current event loop"""
        if self._client is None or self._client.is_closed:
            self._client = http_utils.create_client(timeout=self.timeout)
        return self._client

    async def close(self):
        # Stop log batching and flush remaining
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        # Final flush
        await self._flush_logs()

        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # --- Auth Helpers ---

    def set_token(self, token: str | None) -> None:
        if token:
            identity_service.store.save_cloud_token(token)
        else:
            identity_service.store.delete_cloud_token()

    def get_token(self) -> str | None:
        return identity_service.get_cloud_token()

    def get_member_id(self) -> int | None:
        return identity_service.get_member_id()

    def _load_token(self):
        # Deprecated: Now handled by IdentityService/IdentityStore
        pass

    def _save_token(self, token: str, member_id: int):
        # Deprecated: Use IdentityService.login_with_cloud_result or IdentityStore directly
        identity_service.store.save_cloud_token(token)
        identity_service.store.save_member_id(member_id)

    def logout(self):
        identity_service.logout()

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
        active_token = token or self.get_token()

        # Split-Proxy Logic: Determine prefix based on endpoint
        # Routes starting with /api/v1 (except specific legacy) or specific gateway patterns
        gateway_prefixes = ["/api/v1/user", "/api/v1/quota", "/api/v1/auth/verify", "/ws", "/health"]
        is_gateway = any(endpoint.startswith(p) for p in gateway_prefixes)

        root_url = self.root_url

        if is_gateway:
            current_base = f"{root_url}/gateway"
        else:
            current_base = f"{root_url}/member"

        url = f"{current_base}{endpoint}"
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
            data = res.get("data", {})
            token = data.get("token")
            if token:
                member_id = data.get("member_id", 0)
                self._save_token(token, member_id)
                return {"success": True, "token": token, "member_id": member_id, "data": data}
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
            data = res.get("data", {})
            token = data.get("token")
            if token:
                member_id = data.get("member_id", 0)
                self._save_token(token, member_id)
                return {
                    "success": True,
                    "token": token,
                    "member_id": member_id,
                    "data": data,
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

    async def change_password(self, old_password: str, new_password: str, token: str | None = None) -> dict[str, Any]:
        """Change password for logged-in user."""
        return await self.request(
            "POST",
            "/passport/api/password/change",
            data={"old_password": old_password, "new_password": new_password},
            token=token,
        )

    async def update_user_info(self, data: dict[str, Any], token: str | None = None) -> dict[str, Any]:
        """Update current user info."""
        return await self.request(
            "POST",
            "/api/member/update",
            data=data,
            token=token,
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

    # ==================== Subscription APIs ====================

    async def get_subscription_status(self) -> dict:
        """获取会员订阅状态"""
        return await self.request("GET", "/subscription/api/subscription/status")

    async def get_subscription_permissions(self) -> dict:
        """获取会员功能权限"""
        return await self.request("GET", "/subscription/api/subscription/permissions")

    async def check_feature_permission(self, feature: str) -> dict:
        """检查特定功能权限"""
        return await self.request(
            "POST", 
            "/subscription/api/subscription/checkPermission",
            data={"feature": feature}
        )

    async def validate_feature_access(self, required_feature: str) -> dict:
        """验证访问权限（详细版）"""
        return await self.request(
            "POST",
            "/subscription/api/subscription/validateAccess",
            data={"required_feature": required_feature}
        )

    async def get_subscription_plans(self) -> dict:
        """获取可用订阅计划列表"""
        return await self.request("GET", "/subscription/api/subscription/plans")

    async def calculate_upgrade_price(self, target_level_id: int) -> dict:
        """计算升级价格预览（支付前调用）"""
        return await self.request(
            "POST",
            "/subscription/api/plan/calculateUpgradePrice",
            data={"target_level_id": target_level_id}
        )

    async def create_subscription_order(self, level_id: int, auto_renew: bool = False) -> dict:
        """创建订阅订单"""
        return await self.request(
            "POST",
            "/subscription/api/subscription/createOrder",
            data={"level_id": level_id, "auto_renew": 1 if auto_renew else 0, "app_type": "pc"}
        )

    async def check_subscription_order_status(self, order_id: str) -> dict:
        """检查订阅订单支付状态"""
        return await self.request(
            "GET", 
            "/subscription/api/order/checkStatus",
            params={"order_id": order_id}
        )

    async def get_subscription_detail(self) -> dict:
        """获取订阅详情"""
        return await self.request("GET", "/subscription/api/subscription/getDetail")

    async def cancel_subscription(self, cancel_type: str = "expire", reason: str = "") -> dict:
        """取消订阅"""
        return await self.request("POST", "/subscription/api/subscription/cancel", data={
            "cancel_type": cancel_type,
            "reason": reason
        })

    async def get_ai_quota(self) -> dict:
        """获取 AI 配额（统一配额池）"""
        return await self.request("GET", "/subscription/api/aiQuota")

    async def get_all_ai_quotas(self) -> dict:
        """获取所有 AI 配额 (目前与 get_ai_quota 相同)"""
        return await self.get_ai_quota()

    async def consume_ai_quota(self, count: int = 1, metadata: dict | None = None) -> dict:
        """消耗 AI 配额（统一配额池）"""
        return await self.request("POST", "/subscription/api/aiQuota/consumeQuota", data={
            "count": count
        })

    async def get_ai_quota_history(self, page: int = 1, page_size: int = 20) -> dict:
        """获取 AI 配额使用历史"""
        params = {"page": page, "page_size": page_size}
        return await self.request("GET", "/subscription/api/aiQuota/getUsageHistory", params=params)

    # ==================== LLM Platform APIs ====================

    async def get_llm_models(self) -> dict:
        """
        从 EvoLoop Gateway 获取 LLM 和 Embedding 模型列表
        
        Returns:
            {"code": 0, "data": {"models": [...]}, "message": "..."}
        """
        return await self.request("GET", "/evolooplink/api/llm/getModels")

    # ==================== Log APIs ====================

    async def upload_log(self, device_id, thread_id, log_type, content, name=None, command_id=None, project_id=None):
        content_str = json_utils.dumps(content) if isinstance(content, dict | list) else str(content)

        # MySQL TEXT limit is 65535 bytes. Truncate aggressively to 60,000 bytes.
        encoded_content = content_str.encode('utf-8')
        if len(encoded_content) > 60000:
            content_str = encoded_content[:60000].decode('utf-8', errors='ignore') + "\n...[TRUNCATED BY EVOLOOP DUE TO CLOUD SIZE LIMITS]"

        data = {
            "device_id": device_id,
            "thread_id": thread_id,
            "type": log_type,
            "name": name,
            "content": content_str,
            "create_time": int(time.time() * 1000)
        }
        if command_id:
            data["command_id"] = command_id
        if project_id:
            data["project_id"] = project_id

        try:
            # If queue is getting full, trigger immediate flush
            if self._log_queue.qsize() > 100:
                if self._flush_task is None or self._flush_task.done():
                    self._flush_task = asyncio.create_task(self._process_log_queue())

            # Non-blocking put
            self._log_queue.put_nowait(data)
        except asyncio.QueueFull:
            logger.warning("[EvoCloud] Log queue full, dropping log entry")

        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._process_log_queue())

    async def _process_log_queue(self):
        """Background loop to flush logs periodically."""
        try:
            while True:
                await asyncio.sleep(2.0)  # Batch interval
                await self._flush_logs()
        except asyncio.CancelledError:
            await self._flush_logs()
        except Exception as e:
            logger.error(f"[EvoCloud] Log queue processor error: {e}")

    async def _flush_logs(self):
        """Internal method to flush current queue to API."""
        if self._log_queue.empty():
            return

        logger.debug(f"[EvoCloud] Flushing {self._log_queue.qsize()} logs from queue...")

        # Drain queue up to 50 items
        logs_buffer = []
        while not self._log_queue.empty() and len(logs_buffer) < 50:
            logs_buffer.append(await self._log_queue.get())

        if not logs_buffer:
            return

        # Group by device_id to ensure safe batching
        batches = {}
        for log in logs_buffer:
            did = log.get("device_id")
            if did not in batches:
                batches[did] = []
            batches[did].append(log)

        # Send batches
        for did, batch in batches.items():
            try:
                # Use batchUpload endpoint
                # Log.php expects device_id at top level for permission check
                # We put it in BOTH body and query params to ensure BaseApi validation passes
                payload = {
                     "device_id": did,
                     "logs": batch
                }

                query_params = {"device_id": did}

                # Also pass project_id if consistent
                if batch and batch[0].get("project_id"):
                    pid = batch[0].get("project_id")
                    payload["project_id"] = pid
                    query_params["project_id"] = pid

                res = await self.request(
                    "POST",
                    "/evolooplink/api/log/upload",
                    params=query_params,
                    data=payload
                )

                if res.get("code", -1) < 0:
                    logger.warning(f"[EvoCloud] Batch upload failed for device {did}: {res.get('message')}")
            except Exception as e:
                logger.error(f"[EvoCloud] Error in batch log upload for device {did}: {e}")
