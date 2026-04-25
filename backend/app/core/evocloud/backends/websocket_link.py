import asyncio
import json
import logging
import os
import platform
import ssl
from collections import deque
from collections.abc import Callable
from typing import Any

import certifi
import websockets
from websockets.client import ClientConnection

from app.core.evocloud.interfaces.client import EvoCloudClientProtocol
from app.core.evocloud.interfaces.link import DeviceLinkProtocol
from app.core.evocloud.schemas import (
    EvoCloudConfig,
    ProjectSwitchEvent,
    QueryResponse,
    RemoteCommand,
    WebSocketHandshake,
    WebSocketPing,
)
from app.core.identity import identity_service
from app.utils import file as file_utils
from app.utils.async_utils import run_in_thread
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


class EvoCloudWebSocketLink(DeviceLinkProtocol):
    """
    Standardized WebSocket Link for EvoCloud.
    """

    def __init__(self, config: EvoCloudConfig, api_client: EvoCloudClientProtocol):
        self.config = config
        self.api = api_client

        # Device Identity
        self.device_name = self.config.device_name or f"{platform.node()}"

        # Token change -> auto reconnect
        self.api.on_token_change(self._on_token_changed)

        # State
        self.client_id: str | None = None

        # Connection
        self.ws: ClientConnection | None = None
        self._running = False
        self._reconnect_delay = 5

        # Callbacks
        self._command_handler: Callable[[RemoteCommand], None] | None = None
        self._event_handler: Callable[[str, ProjectSwitchEvent], None] | None = None
        self._query_handler: Callable[[str, str, dict[str, Any]], Any] | None = None

        # Idempotency & Concurrency
        self._processed_commands: deque[str | int] = deque(maxlen=500)
        self._command_semaphore = asyncio.Semaphore(5)

    @property
    def device_key(self) -> str:
        return self._get_or_create_device_key()

    def _get_or_create_device_key(self) -> str:
        # 1. Try secure storage first
        dk = identity_service.store.get_device_key()
        if dk:
            return dk

        # 2. Migration: Try legacy file
        base_dir = self.config.app_data_dir or os.path.expanduser("~")
        key_file = os.path.join(base_dir, ".evoloop_device_key")

        legacy_file = os.path.expanduser("~/.evoloop_device_key")
        if not os.path.exists(key_file) and os.path.exists(legacy_file):
            key_file = legacy_file

        if os.path.exists(key_file):
            dk = file_utils.read_file(key_file).strip()
            # Migrate to Keychain
            identity_service.store.save_device_key(dk)
            try:
                os.remove(key_file)
                logger.info(f"Migrated device key from {key_file} to secure storage")
            except Exception as e:
                logger.warning(f"Failed to remove legacy key file: {e}")
            return dk

        # 3. Create New
        dk = gen_uuid()
        identity_service.store.save_device_key(dk)
        return dk

    def set_command_handler(self, handler: Callable):
        self._command_handler = handler

    def set_event_handler(self, handler: Callable):
        self._event_handler = handler

    async def bind_client_id(self, client_id: str):
        """Bind a mobile client to this device via HTTP API."""
        if self.device_key is not None:
            await self.api.bind_client_id(self.device_key, client_id)
        else:
            logger.warning("[EvoCloud] Cannot bind client: device_key not available")

    def set_query_handler(self, handler: Callable):
        """设置查询处理器 (query_type, thread_id, params) -> result"""
        self._query_handler = handler

    def is_connected(self) -> bool:
        if not self._running or self.ws is None:
            return False
        return self.ws.state == websockets.State.OPEN

    async def send_message(self, message: dict | str):
        """Send message to Cloud via WebSocket."""
        if not self.is_connected() or not self.ws:
            return False

        try:
            payload = message if isinstance(message, str) else json.dumps(message)
            await self.ws.send(payload)
            return True
        except Exception as e:
            logger.warning(f"[EvoCloud] WS Send Error: {e}")
            return False

    async def start(self):
        """Start the WebSocket connection and Heartbeat Loops.

        Note: Device registration is now done via WebSocket handshake.
        HTTP registration is removed in favor of pure WebSocket architecture.
        """
        if self._running:
            return

        if not self.api.get_token():
            logger.warning("[EvoCloud] Cannot start Device Link: No Token")
            return

        self._running = True

        logger.info(f"[EvoCloud] Starting Device Link (device_key={self.device_key})...")
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._ws_connect_loop())

    async def stop(self):
        self._running = False
        if self.ws:
            try:
                # Close with timeout to avoid hanging
                await asyncio.wait_for(self.ws.close(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.debug("[EvoCloud] WS close timed out, forcing disconnect")
            except Exception as e:
                logger.debug(f"[EvoCloud] Error closing WS: {e}")
            finally:
                self.ws = None

    async def _heartbeat_loop(self):
        """Send WebSocket ping messages to keep connection alive.

        Replaces HTTP heartbeat with WebSocket ping/pong.
        """
        while self._running:
            if self.ws and self.is_connected():
                try:
                    # Send ping via WebSocket
                    ping_msg = WebSocketPing(timestamp=int(asyncio.get_running_loop().time()))
                    await self.ws.send(json.dumps(ping_msg.model_dump()))
                    logger.debug("[EvoCloud] WebSocket ping sent")
                except Exception as e:
                    logger.debug(f"[EvoCloud] WebSocket ping failed: {e}")
            await asyncio.sleep(30)

    async def _ws_connect_loop(self):
        retry_count = 0
        base_delay = 5
        max_delay = 60

        # SSL context for WebSocket connection
        ssl_context = None
        if self.config.ws_url.startswith("wss://"):
            if not self.config.ssl_verify:
                # Create unverified SSL context for development
                ssl_context = ssl._create_unverified_context()
                logger.debug("[EvoCloud] SSL verification disabled for WebSocket (unverified context)")
            else:
                # Use certifi to ensure we have valid CA certificates
                ssl_context = ssl.create_default_context(cafile=certifi.where())

        while self._running:
            try:
                logger.info(f"[EvoCloud) Connecting WS to {self.config.ws_url}...")

                async with websockets.connect(self.config.ws_url, ssl=ssl_context) as ws:
                    self.ws = ws
                    logger.info("[EvoCloud] WS Connected. Sending handshake...")

                    # New Go Gateway Handshake
                    handshake = WebSocketHandshake(payload={
                        "device_type": "agent",
                        "device_key": self.device_key,
                        "token": self.api.get_token()
                    })
                    await ws.send(json.dumps(handshake.model_dump()))

                    retry_count = 0  # Reset on success
                    async for message in ws:
                        await self._handle_ws_message(str(message))
            except ssl.SSLError as e:
                logger.error(f"[EvoCloud] SSL Certificate Error: {e}")
                if not self.config.ssl_verify:
                    logger.error("[EvoCloud] SSL verification is already disabled, but error persists")
                else:
                    logger.info("[EvoCloud] Tip: Set EVOCLOUD_SSL_VERIFY=false to disable SSL verification (development only)")
            except asyncio.CancelledError:
                raise  # Let cancellation propagate cleanly
            except Exception as e:
                logger.warning(f"[EvoCloud] WS Connection Error: {e}")
            finally:
                self.ws = None

            if self._running:
                # Exponential backoff
                delay = min(max_delay, base_delay * (2 ** retry_count))
                logger.info(f"[EvoCloud] Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                retry_count += 1

    async def _handle_ws_message(self, message: str):
        logger.info(f"[EvoCloud] WS RECV: {message[:500]}")
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "init":
                init_data = data.get("data", {})
                client_id = init_data.get("client_id")

                if client_id:
                    self.client_id = client_id

            elif msg_type == "new_command":
                cmd = data.get("data", {})
                cmd_id = cmd.get("command_id")
                thread_id = cmd.get("thread_id")
                logger.info(f"[EvoCloud] NEW_COMMAND received: cmd_id={cmd_id}, thread_id={thread_id}, handler_set={self._command_handler is not None}")

                # 立即发送 command_ack 给 Gateway
                ack_msg = {
                    "type": "command_ack",
                    "data": {
                        "command_id": cmd_id,
                        "thread_id": thread_id,
                        "status": "received",
                    },
                }
                asyncio.create_task(self.send_message(ack_msg))
                logger.info(f"[EvoCloud] command_ack sent: cmd_id={cmd_id}")

                if not self._command_handler:
                    logger.warning("[EvoCloud] NEW_COMMAND ignored: no command handler registered")
                    return

                if cmd_id and cmd_id in self._processed_commands:
                    logger.info(f"[EvoCloud] NEW_COMMAND skipped (duplicate): cmd_id={cmd_id}")
                    return
                if cmd_id:
                    self._processed_commands.append(cmd_id)

                logger.info(f"[EvoCloud] NEW_COMMAND dispatching: cmd_id={cmd_id}")
                asyncio.create_task(self._execute_command_wrapper(cmd))

            elif msg_type == "project_switch":
                if self._event_handler:
                    event_data = ProjectSwitchEvent.model_validate(data.get("data", {}))
                    if asyncio.iscoroutinefunction(self._event_handler):
                        asyncio.create_task(self._safe_event_handler(msg_type, event_data))
                    else:
                        try:
                            self._event_handler(msg_type, event_data)
                        except Exception as e:
                            logger.error(f"[EvoCloud] Project switch handler error: {e}")

            elif msg_type == "query":
                await self._handle_query(data)
            else:
                logger.warning(f"[EvoCloud] Unhandled WS message type: {msg_type}")

        except Exception as e:
            logger.error(f"[EvoCloud] WS Handle Error: {e}")

    async def _handle_query(self, data: dict):
        """处理来自 Gateway 的查询请求"""
        request_id = data.get("request_id")
        query_data = data.get("data", {})
        query_type = query_data.get("query_type")
        thread_id = query_data.get("thread_id")
        params = query_data.get("params", {})

        logger.debug(f"[EvoCloud] Query request: {query_type} (req_id={request_id})")

        result = None
        error = None

        try:
            if self._query_handler:
                if asyncio.iscoroutinefunction(self._query_handler):
                    result = await self._query_handler(query_type, thread_id, params)
                else:
                    result = await run_in_thread(self._query_handler, query_type, thread_id, params)
            else:
                error = "Query handler not registered"
        except Exception as e:
            logger.error(f"[EvoCloud] Query error: {e}")
            error = str(e)

        # 发送响应
        response = QueryResponse(
            request_id=request_id,
            data={
                "code": 0 if error is None else 500,
                "message": error or "success",
                "request_id": request_id,
                "data": result,
            },
        )
        await self.send_message(response.model_dump())

    async def _safe_event_handler(self, event_type: str, event_data: ProjectSwitchEvent):
        """Wrap event handler with error logging for asyncio.create_task safety."""
        try:
            if self._event_handler:
                await self._event_handler(event_type, event_data)
        except Exception as e:
            logger.error(f"[EvoCloud] Project switch handler error: {e}")

    def _on_token_changed(self, token: str | None):
        """Callback invoked when the access token changes. Triggers reconnect
        so the next handshake uses the latest token."""
        if not self._running or not self.ws or not token:
            return
        logger.info("[EvoCloud] Token changed, triggering reconnect to use new token...")
        try:
            asyncio.get_running_loop().create_task(self._force_reconnect())
        except RuntimeError:
            pass

    async def _force_reconnect(self):
        """Force close current WebSocket connection to trigger reconnect.

        Used when a command times out or the connection is stuck,
        to let Gateway detect disconnect and clean up device status.
        """
        logger.warning("[EvoCloud] Force reconnect triggered due to stuck command/timeout")
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.debug(f"[EvoCloud] Error during force reconnect close: {e}")
        self.ws = None

    async def _execute_command_wrapper(self, cmd_data: dict):
        cmd_id = cmd_data.get("command_id")
        logger.info(f"[EvoCloud] Command execution START: cmd_id={cmd_id}")

        async def _run():
            async with self._command_semaphore:
                logger.info(f"[EvoCloud] Command status update -> RUNNING: cmd_id={cmd_id}")
                await self.api.update_command_status(cmd_id, 2)  # Running
                try:
                    if self._command_handler:
                        command = RemoteCommand.model_validate(cmd_data)
                        logger.info(f"[EvoCloud] Command handler invoking: cmd_id={cmd_id}, type={command.type}")
                        if asyncio.iscoroutinefunction(self._command_handler):
                            await self._command_handler(command)
                        else:
                            await run_in_thread(self._command_handler, command)
                    logger.info(f"[EvoCloud] Command execution SUCCESS: cmd_id={cmd_id}")
                    await self.api.update_command_status(cmd_id, 3)  # Completed
                except Exception as e:
                    logger.error(f"[EvoCloud] Command execution FAILED: cmd_id={cmd_id}, error={e}")
                    await self.api.update_command_status(cmd_id, 4, str(e))  # Failed

        try:
            await asyncio.wait_for(_run(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.error(f"[EvoCloud] Command execution TIMEOUT: cmd_id={cmd_id}")
            try:
                await self.api.update_command_status(cmd_id, 4, "execution timeout")
            except Exception as e:
                logger.error(f"[EvoCloud] Failed to update timeout status: {e}")
            # 修复 3：超时后触发强制重连，让 Gateway 清理 busy 状态
            asyncio.create_task(self._force_reconnect())
