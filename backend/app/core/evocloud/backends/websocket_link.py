import asyncio
import json
import logging
import os
import platform
from collections.abc import Callable
from typing import Any

import websockets
from websockets.legacy.client import WebSocketClientProtocol

from app.core.evocloud.interfaces.client import EvoCloudClientProtocol
from app.core.evocloud.interfaces.link import DeviceLinkProtocol
from app.core.evocloud.schemas import EvoCloudConfig
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
        self.device_key = self._get_or_create_device_key()

        # State
        # State
        self._device_id: int | None = None
        self.client_id: str | None = None

        # Connection
        self.ws: WebSocketClientProtocol | None = None
        self._running = False
        self._reconnect_delay = 5

        # Callbacks
        self._command_handler: Callable[[dict[str, Any]], None] | None = None
        self._event_handler: Callable[[str, dict[str, Any]], None] | None = None

        # Idempotency
        self._processed_commands: set[int] = set()

    @property
    def device_id(self) -> int | None:
        return self._device_id

    def _get_or_create_device_key(self) -> str:
        # TODO: This should probably also be configurable path or abstracted
        key_file = os.path.expanduser("~/.evoloop_device_key")
        if os.path.exists(key_file):
            return file_utils.read_file(key_file).strip()
        else:
            dk = gen_uuid()
            file_utils.write_file(key_file, dk)
            return dk

    def set_command_handler(self, handler: Callable):
        self._command_handler = handler

    def set_event_handler(self, handler: Callable):
        self._event_handler = handler

    def is_connected(self) -> bool:
        return self._running and (self.ws is not None)

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
        """Start the WebSocket connection and Heartbeat Loops."""
        if self._running:
            return

        if not self.api.get_token():
            logger.warning("[EvoCloud] Cannot start Device Link: No Token")
            return

        self._running = True

        # Register Device via API
        success = await self._register_device()
        if not success:
            logger.error("[EvoCloud] Device registration failed. Aborting Link.")
            self._running = False
            return

        logger.info("[EvoCloud] Starting Device Link Loops...")
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._ws_connect_loop())

    async def stop(self):
        self._running = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.warning(f"Error closing WS: {e}")
            self.ws = None

    async def _register_device(self) -> bool:
        os_info = f"{platform.system()} {platform.release()}"
        res = await self.api.register_device(self.device_key, self.device_name, os_info)

        if res.get("code") == 0:
            self._device_id = res["data"]["device_id"]
            logger.info(f"[EvoCloud] Device Registered ID: {self._device_id}")
            return True

    async def _heartbeat_loop(self):
        while self._running:
            if self._device_id:
                try:
                    await self.api.send_heartbeat(self._device_id)
                except Exception as e:
                    logger.debug(f"Heartbeat failed: {e}")
            await asyncio.sleep(30)
 
    async def _ws_connect_loop(self):
        retry_count = 0
        base_delay = 5
        max_delay = 60

        while self._running:
            try:
                logger.info(f"[EvoCloud) Connecting WS to {self.config.ws_url}...")
                
                async with websockets.connect(self.config.ws_url) as ws:
                    self.ws = ws
                    logger.info("[EvoCloud] WS Connected")
                    retry_count = 0  # Reset on success
                    async for message in ws:
                        await self._handle_ws_message(str(message))
            except Exception as e:
                logger.warning(f"[EvoCloud] WS Connection Error: {e}")

            if self._running:
                # Exponential backoff
                delay = min(max_delay, base_delay * (2 ** retry_count))
                logger.info(f"[EvoCloud] Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                retry_count += 1

    async def _handle_ws_message(self, message: str):
        logger.debug(f"[EvoCloud] Incoming WS Message: {message}")
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "init":
                client_id = data.get("data", {}).get("client_id")
                if client_id:
                    await self._bind_client_id(client_id)

            elif msg_type == "new_command":
                cmd = data.get("data", {})
                cmd_id = cmd.get("command_id")
                if cmd_id and cmd_id in self._processed_commands:
                    logger.debug(f"[EvoCloud] Skipping duplicate command: {cmd_id}")
                    return
                if cmd_id:
                    self._processed_commands.add(cmd_id)
                    # Limit cache size
                    if len(self._processed_commands) > 500:
                        # Convert to list to remove oldest, or just clear if too big
                        # Simple approach: clear half to avoid frequent re-alloc
                        self._processed_commands = set(list(self._processed_commands)[250:])

                if self._command_handler:
                    asyncio.create_task(self._execute_command_wrapper(cmd))

            elif msg_type == "project_switch":
                if self._event_handler:
                    if asyncio.iscoroutinefunction(self._event_handler):
                        asyncio.create_task(self._event_handler(msg_type, data.get("data", {})))
                    else:
                        self._event_handler(msg_type, data.get("data", {}))

        except Exception as e:
            logger.error(f"[EvoCloud] WS Handle Error: {e}")

    async def _bind_client_id(self, client_id: str):
        if not self._device_id:
            return
        try:
            await self.api.bind_client_id(self._device_id, client_id)
            self.client_id = client_id
            logger.info(f"[EvoCloud] Bound Client ID: {client_id}")
        except Exception as e:
            logger.error(f"Failed to bind client ID: {e}")

    async def _execute_command_wrapper(self, cmd_data):
        cmd_id = cmd_data.get("command_id")
        await self.api.update_command_status(cmd_id, 2)  # Running
        try:
            if self._command_handler:
                if asyncio.iscoroutinefunction(self._command_handler):
                    await self._command_handler(cmd_data)
                else:
                    await run_in_thread(self._command_handler, cmd_data)
            await self.api.update_command_status(cmd_id, 3)  # Completed
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            await self.api.update_command_status(cmd_id, 4, str(e))  # Failed
