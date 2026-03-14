"""
Cloud Client for EvoLoop.

Provides HTTP and WebSocket connectivity to EvoLoop Cloud services
from the client device.
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from app.core.config import settings
from app.logging import logger

from .protocol import (
    AgentRequest,
    AgentResponse,
    CloudMessage,
    DeviceCredentials,
    DeviceRegistration,
    ErrorCode,
    get_error_message,
    MemoryRecallRequest,
    MemoryRecallResponse,
    MessageType,
    SkillDownloadRequest,
    SkillPackage,
)


@dataclass
class CloudClientConfig:
    """Configuration for CloudClient."""
    base_url: str
    device_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None

    # Connection settings
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0

    # WebSocket settings
    ws_reconnect_interval: float = 5.0
    ws_heartbeat_interval: float = 30.0


class CloudClient:
    """
    Client for EvoLoop Cloud API.

    Provides:
    - HTTP REST API calls
    - WebSocket real-time communication
    - Automatic retry and reconnection
    - Token refresh
    """

    def __init__(self, config: CloudClientConfig | None = None):
        self.config = config or CloudClientConfig(
            base_url=settings.EVOLOOP_CLOUD_URL,
            device_id=settings.DEVICE_ID,
        )

        # HTTP client
        self._http: httpx.AsyncClient | None = None

        # WebSocket
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._ws_task: asyncio.Task | None = None
        self._ws_connected = False
        self._ws_callbacks: dict[MessageType, list[Callable]] = {}

        # State
        self._closed = True
        self._message_handlers: dict[str, asyncio.Future] = {}

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def connect(self):
        """Initialize HTTP client."""
        if self._http is not None:
            return

        headers = {}
        if self.config.access_token:
            headers["Authorization"] = f"Bearer {self.config.access_token}"

        self._http = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers=headers,
            timeout=self.config.timeout,
        )
        self._closed = False
        logger.info(f"[CloudClient] HTTP client initialized: {self.config.base_url}")

    async def close(self):
        """Close all connections."""
        self._closed = True

        # Close WebSocket
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

        # Close HTTP
        if self._http:
            await self._http.aclose()
            self._http = None

        logger.info("[CloudClient] All connections closed")

    # ========== Device Registration ==========

    async def register_device(self, registration: DeviceRegistration) -> DeviceCredentials:
        """
        Register this device with EvoLoop Cloud.

        Returns credentials for subsequent API calls.
        """
        response = await self._post(
            "/cloud/device/register",
            registration.to_dict(),
            auth=False,  # No auth needed for registration
        )

        credentials = DeviceCredentials.from_dict(response)
        self.config.device_id = credentials.device_id
        self.config.access_token = credentials.access_token
        self.config.refresh_token = credentials.refresh_token

        # Update HTTP client with new token
        if self._http:
            self._http.headers["Authorization"] = f"Bearer {credentials.access_token}"

        logger.info(f"[CloudClient] Device registered: {credentials.device_id}")
        return credentials

    async def refresh_token(self) -> str:
        """
        Refresh access token using refresh token.

        Returns new access token.
        """
        if not self.config.refresh_token:
            raise CloudClientError(
                ErrorCode.AUTH_TOKEN_EXPIRED,
                "No refresh token available"
            )

        response = await self._post(
            "/cloud/device/refresh",
            {"refresh_token": self.config.refresh_token},
            auth=False,
        )

        self.config.access_token = response["access_token"]
        self.config.refresh_token = response.get("refresh_token", self.config.refresh_token)

        # Update HTTP client
        if self._http:
            self._http.headers["Authorization"] = f"Bearer {self.config.access_token}"

        return self.config.access_token

    # ========== Agent API ==========

    async def agent_plan(
        self,
        session_id: str,
        intent: str,
        context: dict | None = None,
    ) -> AgentResponse:
        """
        Request execution plan from cloud agent.

        Used when local planning needs cloud intelligence or LTM context.
        """
        request = AgentRequest(
            intent=intent,
            context=context or {},
            local_state={},
            request_type="plan",
        )

        response = await self._post(
            "/cloud/agent/plan",
            {
                "device_id": self.config.device_id,
                "session_id": session_id,
                **request.to_dict(),
            }
        )

        return AgentResponse.from_dict(response["decision"])

    async def agent_decide(
        self,
        session_id: str,
        intent: str,
        local_state: dict,
        context: dict | None = None,
    ) -> AgentResponse:
        """
        Request runtime decision from cloud agent.

        Used during execution when anomaly detected.
        """
        request = AgentRequest(
            intent=intent,
            context=context or {},
            local_state=local_state,
            request_type="decide",
        )

        response = await self._post(
            "/cloud/agent/decide",
            {
                "device_id": self.config.device_id,
                "session_id": session_id,
                **request.to_dict(),
            }
        )

        return AgentResponse.from_dict(response["decision"])

    # ========== Memory API ==========

    async def memory_recall(
        self,
        query: str,
        memory_types: list[str] | None = None,
        limit: int = 10,
    ) -> MemoryRecallResponse:
        """
        Query Long-Term Memory (LTM) on cloud.

        Retrieves relevant memories for current context.
        """
        request = MemoryRecallRequest(
            query=query,
            memory_types=memory_types or ["episodic", "concept"],
            limit=limit,
        )

        response = await self._post(
            "/cloud/memory/recall",
            {
                "device_id": self.config.device_id,
                **request.to_dict(),
            }
        )

        return MemoryRecallResponse.from_dict(response)

    async def atlas_query(
        self,
        app_id: str,
        element_description: str,
        current_screen: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query Atlas for UI element information.

        Returns element candidates from community knowledge.
        """
        response = await self._post(
            "/cloud/memory/atlas/query",
            {
                "device_id": self.config.device_id,
                "app_id": app_id,
                "element_description": element_description,
                "current_screen": current_screen,
            }
        )

        return response.get("candidates", [])

    # ========== Skill API ==========

    async def skill_synthesize(
        self,
        task_name: str,
        description: str,
        video_url: str | None = None,
        event_trace: list | None = None,
        platform: str = "android",
    ) -> str:
        """
        Request skill synthesis from learning materials.

        Returns job ID for polling.
        """
        response = await self._post(
            "/cloud/skill/synthesize",
            {
                "device_id": self.config.device_id,
                "task_name": task_name,
                "description": description,
                "video_url": video_url,
                "event_trace": event_trace or [],
                "platform": platform,
            }
        )

        return response["job_id"]

    async def skill_synthesis_status(self, job_id: str) -> dict[str, Any]:
        """Check status of skill synthesis job."""
        response = await self._get(f"/cloud/skill/synthesis-status/{job_id}")
        return response

    async def skill_download(self, skill_id: str) -> SkillPackage:
        """Download complete skill package."""
        response = await self._get(f"/cloud/skill/download/{skill_id}")
        return SkillPackage.from_dict(response)

    async def skill_list(
        self,
        platform: str | None = None,
        app_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List available skills."""
        params = {}
        if platform:
            params["platform"] = platform
        if app_id:
            params["app_id"] = app_id

        response = await self._get("/cloud/skill/list", params=params)
        return response.get("skills", [])

    # ========== WebSocket ==========

    async def connect_websocket(self):
        """Connect to WebSocket for real-time communication."""
        if self._ws_connected:
            return

        ws_url = self.config.base_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_url}/cloud/ws"

        headers = {}
        if self.config.access_token:
            headers["Authorization"] = f"Bearer {self.config.access_token}"

        try:
            self._ws = await websockets.connect(
                ws_url,
                extra_headers=headers,
            )
            self._ws_connected = True

            # Start message handler
            self._ws_task = asyncio.create_task(self._ws_handler())

            logger.info("[CloudClient] WebSocket connected")

        except Exception as e:
            logger.error(f"[CloudClient] WebSocket connection failed: {e}")
            raise

    async def _ws_handler(self):
        """Handle WebSocket messages."""
        try:
            while self._ws_connected and self._ws:
                try:
                    message_str = await self._ws.recv()
                    message = CloudMessage.from_json(message_str)

                    # Handle by message type
                    await self._handle_ws_message(message)

                except ConnectionClosed:
                    logger.warning("[CloudClient] WebSocket connection closed")
                    break
                except Exception as e:
                    logger.error(f"[CloudClient] WebSocket error: {e}")

        except asyncio.CancelledError:
            logger.info("[CloudClient] WebSocket handler cancelled")

        finally:
            self._ws_connected = False

    async def _handle_ws_message(self, message: CloudMessage):
        """Process incoming WebSocket message."""
        # Check for response to pending request
        if message.message_id in self._message_handlers:
            future = self._message_handlers.pop(message.message_id)
            if not future.done():
                future.set_result(message)
            return

        # Handle server-initiated messages
        callbacks = self._ws_callbacks.get(message.msg_type, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"[CloudClient] Callback error: {e}")

    def on_message(self, msg_type: MessageType, callback: Callable):
        """Register callback for message type."""
        if msg_type not in self._ws_callbacks:
            self._ws_callbacks[msg_type] = []
        self._ws_callbacks[msg_type].append(callback)

    async def send_ws_message(self, message: CloudMessage, wait_for_response: bool = False) -> CloudMessage | None:
        """Send message over WebSocket."""
        if not self._ws_connected or not self._ws:
            raise CloudClientError(
                ErrorCode.NETWORK_UNREACHABLE,
                "WebSocket not connected"
            )

        if wait_for_response:
            future = asyncio.Future()
            self._message_handlers[message.message_id] = future

        await self._ws.send(message.to_json())

        if wait_for_response:
            try:
                return await asyncio.wait_for(future, timeout=self.config.timeout)
            except asyncio.TimeoutError:
                self._message_handlers.pop(message.message_id, None)
                raise CloudClientError(
                    ErrorCode.NETWORK_TIMEOUT,
                    "WebSocket response timeout"
                )

        return None

    # ========== HTTP Helpers ==========

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """HTTP GET with retry."""
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, data: dict, auth: bool = True) -> dict:
        """HTTP POST with retry."""
        return await self._request("POST", path, json=data, auth=auth)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
        auth: bool = True,
    ) -> dict:
        """HTTP request with retry and error handling."""
        if not self._http:
            raise CloudClientError(
                ErrorCode.CLOUD_NOT_CONFIGURED,
                "HTTP client not initialized"
            )

        if auth and not self.config.access_token:
            raise CloudClientError(
                ErrorCode.AUTH_INVALID_TOKEN,
                "No access token available"
            )

        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                response = await self._http.request(
                    method,
                    path,
                    params=params,
                    json=json,
                )

                # Handle auth errors
                if response.status_code == 401:
                    if attempt < self.config.max_retries - 1:
                        await self.refresh_token()
                        continue
                    raise CloudClientError(
                        ErrorCode.AUTH_TOKEN_EXPIRED,
                        "Token expired and refresh failed"
                    )

                # Handle other errors
                if response.status_code >= 400:
                    error_data = response.json() if response.text else {}
                    raise CloudClientError(
                        ErrorCode(error_data.get("error_code", ErrorCode.SERVER_INTERNAL_ERROR)),
                        error_data.get("message", f"HTTP {response.status_code}"),
                    )

                return response.json()

            except httpx.TimeoutException as e:
                last_error = CloudClientError(ErrorCode.NETWORK_TIMEOUT, str(e))

            except httpx.NetworkError as e:
                last_error = CloudClientError(ErrorCode.NETWORK_UNREACHABLE, str(e))

            except CloudClientError:
                raise

            except Exception as e:
                last_error = CloudClientError(ErrorCode.SERVER_INTERNAL_ERROR, str(e))

            # Retry with backoff
            if attempt < self.config.max_retries - 1:
                delay = self.config.retry_delay * (2 ** attempt)
                logger.warning(f"[CloudClient] Retry {attempt + 1}/{self.config.max_retries} after {delay}s")
                await asyncio.sleep(delay)

        raise last_error


class CloudClientError(Exception):
    """Cloud client error with error code."""

    def __init__(self, error_code: ErrorCode, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(f"[{error_code.name}] {message}")

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code.value,
            "error_message": self.message,
            "user_message": get_error_message(self.error_code),
        }


# Global instance
_cloud_client: CloudClient | None = None


def get_cloud_client() -> CloudClient:
    """Get or create global cloud client instance."""
    global _cloud_client
    if _cloud_client is None:
        _cloud_client = CloudClient()
    return _cloud_client


def reset_cloud_client():
    """Reset global cloud client (for testing)."""
    global _cloud_client
    _cloud_client = None
