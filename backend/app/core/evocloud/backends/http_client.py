"""EvoCloud HTTP Client — core request infrastructure and composition."""

import asyncio
import json
import logging
import time
from collections.abc import Callable

import httpx

from app.core.config import settings
from app.core.evocloud.backends._auth_mixin import AuthMixin
from app.core.evocloud.backends._devices_mixin import DevicesMixin
from app.core.evocloud.backends._projects_mixin import ProjectsMixin
from app.core.evocloud.backends._subscription_mixin import SubscriptionMixin
from app.core.evocloud.backends._sync_mixin import SyncMixin
from app.core.evocloud.interfaces.client import EvoCloudClientProtocol
from app.core.evocloud.routes import RouteTarget, get_endpoint_route
from app.core.evocloud.schemas import EvoCloudConfig
from app.core.identity import identity_service
from app.infrastructure.cache import cache
from app.utils.http import create_client as create_http_client
from app.utils.json import dumps
from app.utils.security import generate_hmac_signature

logger = logging.getLogger(__name__)


class EvoCloudHTTPClient(
    AuthMixin,
    ProjectsMixin,
    DevicesMixin,
    SubscriptionMixin,
    SyncMixin,
    EvoCloudClientProtocol,
):
    """Standardized HTTP Client for EvoCloud.

    Composed from domain-specific mixins:
    - AuthMixin: login, tokens, user info, captcha, register
    - ProjectsMixin: projects, tasks, budget, timesheet
    - DevicesMixin: devices, heartbeat, logs, cancellation
    - SubscriptionMixin: subscription, AI quota, LLM models
    - SyncMixin: conversation sync, messages, upload
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
        return self.base_url.rstrip("/")

    def _get_base_url(self, is_gateway: bool) -> str:
        prefix = "/gateway" if is_gateway else "/member"
        return f"{self.root_url}{prefix}"

    async def get_client(self) -> httpx.AsyncClient:
        """Get httpx client bound to current event loop."""
        if self._client is None or self._client.is_closed:
            self._client = create_http_client(timeout=self.timeout)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # --- Auth Helpers ---

    def on_token_change(self, callback: Callable[[str | None], None]) -> None:
        self._token_change_callbacks.append(callback)

    async def set_token(self, token: str, refresh_token: str | None = None):
        """Save tokens to cache-backed storage."""
        if not settings.MULTI_TENANT_MODE:
            if token:
                token = token.strip()
                await identity_service.store.save_access_token(token)
            if refresh_token:
                refresh_token = refresh_token.strip()
                await identity_service.store.save_refresh_token(refresh_token)

        for callback in self._token_change_callbacks:
            try:
                callback(token)
            except (TypeError, ValueError) as e:
                logger.warning(f"Token change callback error: {e}")

    async def get_token(self) -> str | None:
        return await identity_service.get_access_token()

    async def refresh_access_token(self, failed_token: str | None = None) -> str | None:
        """Refresh the access token using the stored refresh_token via Login.php.

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

        async with self._refresh_lock:
            current_token = await self.get_token()
            if failed_token and current_token != failed_token:
                logger.debug("[EvoCloud] Access token was already refreshed by another coroutine")
                return current_token

            lock = cache.lock("evoloop:token_refresh", timeout=10)
            acquired = await lock.acquire(blocking=False)
            if not acquired:
                logger.debug("[EvoCloud] Another process is refreshing token, waiting...")
                await asyncio.sleep(0.5)
                return await self.get_token()

            try:
                current_token = await self.get_token()
                if failed_token and current_token != failed_token:
                    logger.debug("[EvoCloud] Access token was already refreshed by another process")
                    return current_token

                res = await self.request(
                    "POST",
                    "/api/login/refreshToken",
                    data={"refresh_token": refresh_token},
                    token="",
                    headers={"X-Evoloop-Refresh": "true"},
                )
                if res.get("code") == 0:
                    data = res.get("data", {})
                    new_token = data.get("token")
                    new_refresh_token = data.get("refresh_token")
                    if new_token:
                        await self.set_token(new_token, new_refresh_token)
                        logger.debug("[EvoCloud] Successfully refreshed access token")
                        return new_token

                logger.error(f"[EvoCloud] Token refresh failed: {res.get('message', 'Unknown error')}")
                return None
            finally:
                await lock.release()

    async def get_member_id(self, token: str | None = None) -> int | None:
        return await identity_service.get_member_id()

    async def logout(self, token: str | None = None):
        await identity_service.logout()

    # --- Request Core ---

    def _generate_signature(
        self, method: str, uri: str, body: str, timestamp: int
    ) -> str:
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
        _retry_count: int = 0,
    ) -> dict:
        client = await self.get_client()
        if token == "":
            active_token = None
        else:
            active_token = token or await self.get_token()

        is_gateway = get_endpoint_route(endpoint) == RouteTarget.GATEWAY
        current_base = self._get_base_url(is_gateway)

        url = f"{current_base}{endpoint}"
        timestamp = int(time.time())
        body_str = dumps(data) if data else ""

        req_headers = headers or {}
        req_headers.update({"Content-Type": "application/json", "X-Timestamp": str(timestamp)})

        if self.config.api_key and self.config.api_secret:
            req_headers["X-API-Key"] = self.config.api_key
            req_headers["X-Signature"] = self._generate_signature(method, endpoint, body_str, timestamp)

        request_params = params.copy() if params is not None else {}

        if active_token:
            request_params["token"] = active_token

        log_params = {
            k: ("***" if k == "token" and v else v) for k, v in request_params.items()
        }
        logger.debug(f"[EvoCloud] {method} {endpoint} token={active_token[:8] if active_token else 'none'} params={log_params}")

        try:
            resp = await client.request(method, url, params=request_params, json=data, headers=req_headers)
            raw_text = resp.text
            resp_json = (resp.json() if resp.status_code == 200 else None) or {}
            is_token_expired = (
                resp.status_code == 401
                or resp_json.get("code") in [-10009, -10010]
                or resp_json.get("message") == "TOKEN_EXPIRE"
            )
            logger.info(
                f"[EvoCloud] {method} {endpoint} → {resp.status_code} "
                f"code={resp_json.get('code')} "
                f"msg={resp_json.get('message')!r} "
                f"expired={is_token_expired}"
            )
            if is_token_expired and _retry_count < 1:
                stored_token = await self.get_token()
                if token is None or token == "" or token == stored_token:
                    logger.warning(f"[EvoCloud] Token expired during request to {endpoint} (code: {resp_json.get('code')}), attempting refresh...")
                    new_token = await self.refresh_access_token(failed_token=active_token)
                    if new_token:
                        return await self.request(
                            method=method,
                            endpoint=endpoint,
                            params=params,
                            data=data,
                            token=new_token,
                            headers=headers,
                            _retry_count=_retry_count + 1,
                        )
                    else:
                        logger.error(f"[EvoCloud] Token refresh failed for {endpoint}, returning original error")

            if resp.status_code >= 400:
                logger.error(f"[EvoCloud] {method} {endpoint} → {resp.status_code}: {resp.text[:200]}")

            try:
                result = resp.json()
                if result is None:
                    return {"code": -1, "message": "Empty response body"}
                return result
            except json.JSONDecodeError:
                return {"code": -1, "message": f"Invalid JSON: {resp.text[:100]}"}

        except httpx.RequestError as e:
            logger.error(f"Request connection error to {url}: {type(e).__name__}: {e} (repr: {repr(e)}, cause: {repr(e.__cause__)})")
            if _retry_count < 1:
                logger.debug(f"[EvoCloud] Recreating HTTP client and retrying {endpoint}...")
                await self.close()
                return await self.request(
                    method=method,
                    endpoint=endpoint,
                    params=params,
                    data=data,
                    token=token,
                    headers=headers,
                    _retry_count=_retry_count + 1,
                )
            return {"code": -1, "message": str(e)}
        except OSError as e:
            logger.error(f"Request failed: {e}")
            return {"code": -1, "message": str(e)}
