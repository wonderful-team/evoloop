import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import settings
from app.core.evocloud.interfaces.client import EvoCloudClientProtocol
from app.core.evocloud.routes import RouteTarget, get_endpoint_route
from app.core.evocloud.schemas import EvoCloudConfig
from app.core.identity import identity_service
from app.infrastructure.cache import cache
from app.models.schemas.auth import EvoCloudProxyResponse, LoginResult
from app.utils import http as http_utils
from app.utils import json as json_utils
from app.utils.security import generate_hmac_signature
from app.constants import DEFAULT_PROJECT_ID

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
        self._token_change_callbacks: list[Callable[[str | None], None]] = []
        self._refresh_lock = asyncio.Lock()

    @property
    def root_url(self) -> str:
        return self.base_url.rstrip('/')

    def _get_base_url(self, is_gateway: bool) -> str:
        """
        获取请求的基础 URL。
        
        生产环境：使用统一入口，通过 /gateway 和 /member 前缀路由
        本地开发：通过环境变量 EVOCLOUD_GATEWAY_URL / EVOCLOUD_MEMBER_URL 分别配置
        """
        import os
        if is_gateway:
            gateway_url = os.getenv("EVOCLOUD_GATEWAY_URL")
            if gateway_url:
                return gateway_url.rstrip('/')
            prefix = "/gateway"
        else:
            member_url = os.getenv("EVOCLOUD_MEMBER_URL")
            if member_url:
                return member_url.rstrip('/')
            prefix = "/member"
        return f"{self.root_url}{prefix}"

    async def get_client(self) -> httpx.AsyncClient:
        """Get httpx client bound to current event loop"""
        if self._client is None or self._client.is_closed:
            self._client = http_utils.create_client(timeout=self.timeout)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # --- Auth Helpers ---

    def on_token_change(self, callback: Callable[[str | None], None]) -> None:
        self._token_change_callbacks.append(callback)

    async def set_token(self, token: str, refresh_token: str | None = None):
        """Save tokens to cache-backed storage after stripping and fixing URL-decoding issues."""
        if token:
            # Fix common PHP/URL-decoding issue where '+' becomes ' '
            token = token.strip().replace(" ", "+")
            await identity_service.store.save_access_token(token)
        if refresh_token:
            refresh_token = refresh_token.strip().replace(" ", "+")
            await identity_service.store.save_refresh_token(refresh_token)

        # Trigger callbacks
        for callback in self._token_change_callbacks:
            try:
                callback(token)
            except Exception as e:
                logger.warning(f"Token change callback error: {e}")

    async def get_token(self) -> str | None:
        return await identity_service.get_access_token()

    async def refresh_access_token(self, failed_token: str | None = None) -> str | None:
        """
        Refresh the access token using the stored refresh_token via Login.php.

        Uses a two-layer locking strategy:
        1. asyncio.Lock: prevents multiple coroutines in the same process from
           refreshing simultaneously (non-blocking for the event loop).
        2. cache.lock(blocking=False): prevents multiple processes/workers from
           refreshing simultaneously. Uses fcntl (FileCache) or Redis SET NX EX.
        """
        refresh_token = await identity_service.get_refresh_token()
        if not refresh_token:
            logger.warning("[EvoCloud] Missing Refresh Token, cannot refresh session")
            return None

        # Layer 1: In-process coroutine-level protection
        async with self._refresh_lock:
            current_token = await self.get_token()
            if failed_token and current_token != failed_token:
                logger.info("[EvoCloud] Access token was already refreshed by another coroutine")
                return current_token

            # Layer 2: Cross-process protection (non-blocking to avoid event-loop blocking)
            lock = cache.lock("evoloop:token_refresh", timeout=10)
            acquired = await lock.acquire(blocking=False)
            if not acquired:
                logger.info("[EvoCloud] Another process is refreshing token, waiting...")
                await asyncio.sleep(0.5)
                return await self.get_token()

            try:
                # Double-check after acquiring distributed lock
                current_token = await self.get_token()
                if failed_token and current_token != failed_token:
                    logger.info("[EvoCloud] Access token was already refreshed by another process")
                    return current_token

                logger.info("[EvoCloud] Attempting to refresh access token using Refresh Token...")

                # Call Login.refreshToken endpoint
                res = await self.request(
                    "POST",
                    "/api/login/refreshToken",
                    data={"refresh_token": refresh_token},
                    token="",
                    headers={"X-Evoloop-Refresh": "true"}
                )
                if res.get("code") == 0:
                    data = res.get("data", {})
                    new_token = data.get("token")
                    new_refresh_token = data.get("refresh_token")
                    if new_token:
                        await self.set_token(new_token, new_refresh_token)
                        logger.info("[EvoCloud] Successfully refreshed access token")
                        return new_token

                logger.error(f"[EvoCloud] Token refresh failed: {res.get('message', 'Unknown error')}")
                return None
            finally:
                await lock.release()

    async def get_member_id(self) -> int | None:
        return await identity_service.get_member_id()

    async def logout(self):
        await identity_service.logout()

    # --- Request Core ---

    def _generate_signature(self, method: str, uri: str, body: str, timestamp: int) -> str:
        if not self.config.api_secret:
            return ""
        string_to_sign = f"{method}\n{uri}\n{body}\n{timestamp}"
        return generate_hmac_signature(self.config.api_secret, string_to_sign)

    async def request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        data: dict | None = None,
        token: str | None = None,
        headers: dict | None = None,
        _retry_count: int = 0
    ) -> dict:
        client = await self.get_client()
        # If token is explicitly "", we don't fetch from store (used during refresh)
        if token == "":
            active_token = None
        else:
            active_token = token or await self.get_token()

        # Split-Proxy Logic: Determine routing target for endpoint
        is_gateway = get_endpoint_route(endpoint) == RouteTarget.GATEWAY

        # Get base URL with appropriate prefix
        current_base = self._get_base_url(is_gateway)

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

        # Copy params to avoid mutating the original dictionary (especially during retries)
        request_params = params.copy() if params is not None else {}

        if active_token:
            request_params["token"] = active_token

        try:
            resp = await client.request(method, url, params=request_params, json=data, headers=req_headers)
            # Handle token expiration (401 or specific error code)
            resp_json = resp.json() if resp.status_code == 200 else {}
            is_token_expired = (
                resp.status_code == 401 or 
                resp_json.get("code") in [-10009, -10010] or
                resp_json.get("message") == "TOKEN_EXPIRE"
            )
            if is_token_expired and _retry_count < 1:
                stored_token = await self.get_token()
                if token is None or token == "" or token == stored_token:
                    logger.warning(f"[EvoCloud] Token expired during request to {endpoint} (code: {resp_json.get('code')}), attempting refresh...")
                    new_token = await self.refresh_access_token(failed_token=active_token)
                    if new_token:
                        # Retry once with new token
                        return await self.request(
                            method=method,
                            endpoint=endpoint,
                            params=params,
                            data=data,
                            token=new_token,
                            headers=headers,
                            _retry_count=_retry_count + 1
                        )

            if resp.status_code >= 400:
                logger.error(f"API Error {resp.status_code}: {resp.text[:200]}")

            try:
                return resp.json()
            except json.JSONDecodeError:
                return {"code": -1, "message": f"Invalid JSON: {resp.text[:100]}"}

        except httpx.RequestError as e:
            logger.error(f"Request connection error to {url}: {e}")
            return {"code": -1, "message": str(e)}
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return {"code": -1, "message": str(e)}

    # --- Account & Auth Methods ---

    async def login(self, username, password) -> LoginResult:
        res = await self.request("POST", "/api/login/login", data={"username": username, "password": password})
        if res.get("code", -1) >= 0:
            data = res.get("data", {})
            token = data.get("token")
            refresh_token = data.get("refresh_token")
            if token:
                await self.set_token(token, refresh_token)

                # Member Center doesn't return member_id in login response
                # Fetch it from /api/member/info
                try:
                    user_info = await self.get_user_info()
                    if user_info.get("code") == 0:
                        member_id = user_info.get("data", {}).get("member_id", 0)
                    else:
                        member_id = 0
                except Exception:
                    member_id = 0

                # Update store with member_id
                await identity_service.store.save_member_id(member_id)

                return LoginResult(
                    success=True,
                    token=token,
                    member_id=member_id,
                    data=data,
                )
        return LoginResult(success=False, message=res.get("message", "Login failed"))

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
            "source": settings.SERVICE_NAME,
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

    async def get_project_statistics(self, project_id=DEFAULT_PROJECT_ID, token=None) -> dict:
        p = {"project_id": project_id} if project_id is not None else {}
        return await self.request("GET", "/projectmanage/api/project/statistics", params=p, token=token)

    async def get_ai_global_config(self) -> dict:
        return await self.request("GET", "/api/AI/globalConfig")

    # Cancellation
    async def get_cancellation_info(self) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(await self.request("GET", "/membercancel/api/membercancel/info"))

    async def apply_cancellation(self) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(await self.request("POST", "/membercancel/api/membercancel/apply"))

    async def cancel_cancellation_apply(self) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(await self.request("POST", "/membercancel/api/membercancel/cancelApply"))

    # Public / Auth
    async def get_captcha_config(self) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(await self.request("GET", "/api/captcha/config"))

    async def get_captcha(self, captcha_id: str) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(await self.request("GET", "/api/captcha/get", params={"id": captcha_id}))

    async def get_register_config(self) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(await self.request("GET", "/api/register/config"))

    async def get_register_agreement(self) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(await self.request("GET", "/api/register/agreement"))

    async def send_mobile_code(self, mobile: str, captcha_id: str, captcha_code: str, type: str = "login") -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "POST",
                "/api/sms/send",
                data={
                    "mobile": mobile,
                    "captcha_id": captcha_id,
                    "captcha_code": captcha_code,
                    "type": type,
                },
            )
        )

    async def register_mobile(self, data: dict) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(await self.request("POST", "/api/register/mobile", data=data))

    async def register_username(self, data: dict) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(await self.request("POST", "/api/register/account", data=data))

    async def login_mobile(self, mobile: str, key: str, code: str) -> LoginResult:
        res = await self.request(
            "POST",
            "/passport/api/login/mobile",
            data={"mobile": mobile, "key": key, "code": code},
        )
        if res.get("code", -1) >= 0:
            data = res.get("data", {})
            token = data.get("token")
            refresh_token = data.get("refresh_token")
            if token:
                await self.set_token(token, refresh_token)

                # Member Center doesn't return member_id in login response
                # Fetch it from /api/member/info
                try:
                    user_info = await self.get_user_info()
                    if user_info.get("code") == 0:
                        member_id = user_info.get("data", {}).get("member_id", 0)
                    else:
                        member_id = 0
                except Exception:
                    member_id = 0

                # Update store with member_id
                await identity_service.store.save_member_id(member_id)

                return LoginResult(
                    success=True,
                    token=token,
                    member_id=member_id,
                    data=data,
                )
        return LoginResult(success=False, message=res.get("message", "Login failed"))

    async def check_mobile_exist(self, mobile: str) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(await self.request("GET", "/passport/api/mobile/check", params={"mobile": mobile}))

    async def reset_password_by_mobile(self, mobile: str, code: str, key: str, password: str) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "POST",
                "/passport/api/password/reset/mobile",
                data={"mobile": mobile, "code": code, "key": key, "password": password},
            )
        )

    async def change_password(self, old_password: str, new_password: str, token: str | None = None) -> EvoCloudProxyResponse:
        """Change password for logged-in user."""
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "POST",
                "/passport/api/password/change",
                data={"old_password": old_password, "new_password": new_password},
                token=token,
            )
        )

    async def update_user_info(self, data: dict[str, Any], token: str | None = None) -> EvoCloudProxyResponse:
        """Update current user info."""
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "POST",
                "/api/member/update",
                data=data,
                token=token,
            )
        )

    async def get_user_info(self, token: str | None = None) -> EvoCloudProxyResponse:
        """Get current user info from Member Center."""
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "GET",
                "/api/member/info",
                token=token,
            )
        )

    # Device Specific via API
    async def get_devices(self, token: str | None = None) -> dict:
        return await self.request("GET", "/api/v1/devices", token=token)

    async def send_command_to_device(self, device_key: str, cmd_data: dict, token: str | None = None) -> dict:
        data = {"device_key": device_key, **cmd_data}
        return await self.request("POST", "/api/v1/command/execute", data=data, token=token)

    async def get_device_logs(self, device_key: str, limit=20, project_id=None, token: str | None = None) -> dict:
        params = {"device_key": device_key, "limit": limit}
        if project_id is not None:
            params["project_id"] = project_id
        return await self.request("GET", "/evolooplink/api/log/recent", params=params, token=token)

    async def search_device_logs(self, device_key: str, query: str, limit=20, project_id=None, token: str | None = None) -> dict:
        params = {"device_key": device_key, "query": query, "limit": limit}
        if project_id is not None:
            params["project_id"] = project_id
        return await self.request("GET", "/evolooplink/api/log/search", params=params, token=token)

    async def bind_client_id(self, device_key: str, client_id: str) -> dict:
        """Bind a mobile client_id to a device."""
        return await self.request(
            "POST",
            "/api/v1/devices/bind",
            data={"device_key": device_key, "client_id": client_id},
        )

    async def register_device(self, fingerprint: str, name: str, os_info: str) -> dict:
        """Claim a device from the server.

        The server will:
        1. Look up existing device by fingerprint + member_id
        2. Return existing device_key if found
        3. Check device limit and create new device_key if not found
        """
        return await self.request(
            "POST",
            "/api/v1/devices/register",
            data={
                "fingerprint": fingerprint,
                "device_name": name,
                "device_type": "desktop",
                "os_info": os_info,
            },
        )

    async def send_heartbeat(self, device_key: str):
        await self.request("POST", f"/api/v1/devices/{device_key}/heartbeat")

    # ==================== Subscription APIs ====================

    async def get_subscription_status(self) -> dict:
        """获取会员订阅状态"""
        return await self.request("GET", "/subscription/api/subscription/status")

    async def get_subscription_permissions(self) -> dict:
        """获取会员功能权限"""
        return await self.request("GET", "/subscription/api/subscription/permissions")

    async def get_member_benefits(self) -> dict:
        """获取会员完整权益信息"""
        return await self.request("GET", "/subscription/api/subscription/benefits")

    async def check_benefit(self, code: str) -> dict:
        """检查单项权益"""
        return await self.request(
            "POST",
            "/subscription/api/subscription/checkBenefit",
            data={"code": code}
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
        return await self.request("GET", "/subscription/api/aiQuota/getQuota")

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

    # ==================== Conversation Sync APIs (MC Storage) ====================

    async def sync_conversation(self, device_key: str, conversation: dict) -> dict:
        """
        同步单个会话到 MC (Member Center)

        Args:
            device_key: 设备标识
            conversation: 会话数据
                - id: 会话ID
                - project_id: 项目ID
                - title: 标题
                - created_at: 创建时间戳
                - updated_at: 更新时间戳

        Returns:
            {"code": 0, "data": {"conversation_id": "xxx"}}
        """
        data = {
            "device_key": device_key,
            "conversation": conversation,
        }

        return await self.request(
            "POST",
            "/evolooplink/api/sync/conversation",
            data=data
        )

    async def sync_messages(self, device_key: str, thread_id: str, messages: list[dict]) -> dict:
        """
        批量同步消息到 MC

        Args:
            device_key: 设备标识
            thread_id: 会话ID
            messages: 消息数组

        Returns:
            {"code": 0, "data": {"inserted_count": 10}}
        """
        data = {
            "device_key": device_key,
            "thread_id": thread_id,
            "messages": messages,
        }

        return await self.request(
            "POST",
            "/evolooplink/api/sync/messages",
            data=data
        )

    async def sync_full_conversations(self, device_key: str, data: dict) -> dict:
        """
        全量同步会话和消息 (首次同步或重建)

        Args:
            device_key: 设备标识
            data: 包含 conversations 和 messages 的字典
                {
                    "conversations": [...],
                    "messages": [...]
                }

        Returns:
            {"code": 0, "data": {"conversations": 5, "messages": 100}}
        """
        payload = {
            "device_key": device_key,
            "data": data,
        }

        return await self.request(
            "POST",
            "/evolooplink/api/sync/full",
            data=payload
        )

    async def check_sync_status(self, device_key: str, conversation_ids: list[str]) -> dict:
        """
        检查会话同步状态

        Args:
            device_key: 设备标识
            conversation_ids: 会话ID列表

        Returns:
            {
                "code": 0,
                "data": {
                    "status": {
                        "conv_xxx": {"exists": true, "message_count": 50},
                        "conv_yyy": {"exists": false}
                    }
                }
            }
        """
        return await self.request(
            "GET",
            "/evolooplink/api/sync/status",
            params={"device_key": device_key, "conversation_ids": conversation_ids}
        )

    async def get_conversations(self, project_id: int = DEFAULT_PROJECT_ID, page: int = 1, page_size: int = 20) -> dict:
        """
        获取我的会话列表 (Mobile 也会用此方法)

        Args:
            project_id: 项目ID筛选
            page: 页码
            page_size: 每页数量

        Returns:
            {"code": 0, "data": {"list": [...], "total": 100}}
        """
        params = {
            "page": page,
            "page_size": page_size,
        }
        if project_id > 0:
            params["project_id"] = project_id

        return await self.request(
            "GET",
            "/evolooplink/api/conversation/list",
            params=params
        )

    async def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        before_message_id: str | None = None
    ) -> dict:
        """
        获取会话消息历史

        Args:
            conversation_id: 会话ID
            limit: 数量限制
            before_message_id: 分页用

        Returns:
            {"code": 0, "data": {"conversation": {...}, "messages": [...]}}
        """
        params = {
            "conversation_id": conversation_id,
            "limit": limit,
        }
        if before_message_id:
            params["before_message_id"] = before_message_id

        return await self.request(
            "GET",
            "/evolooplink/api/conversation/messages",
            params=params
        )
