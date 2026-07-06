import asyncio
import json
import logging
import os
import platform
import ssl
import time
from collections import deque
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import certifi
import websockets
from websockets.client import ClientConnection

from app.core.config import settings
from app.core.evocloud.interfaces.client import EvoCloudClientProtocol
from app.core.evocloud.interfaces.link import DeviceLinkProtocol
from app.core.evocloud.schemas import (
    EvoCloudConfig,
)
from app.core.fingerprint import get_hardware_fingerprint
from app.core.identity import identity_service
from app.core.schemas.canonical import (
    MessageType,
    create_envelope,
    is_canonical_envelope,
)

logger = logging.getLogger(__name__)


class EvoCloudWebSocketLink(DeviceLinkProtocol):
    """
    Standardized WebSocket Link for EvoCloud.
    """

    def __init__(self, config: EvoCloudConfig, api_client: EvoCloudClientProtocol):
        self.config = config
        self.api = api_client

        # Token change -> auto reconnect
        self.api.on_token_change(self._on_token_changed)

        # State
        self.client_id: str | None = None
        self._handshake_completed = False

        # Connection
        self.ws: ClientConnection | None = None
        self._running = False
        self._reconnect_delay = 5

        # Idempotency & Concurrency
        self._processed_commands: deque[str | int] = deque(maxlen=500)
        self._command_semaphore = asyncio.Semaphore(5)

        # Send queue for offline buffering
        self._send_queue: asyncio.Queue[dict | str] = asyncio.Queue(maxsize=1000)
        self._send_queue_task: asyncio.Task | None = None

        # Rate-limit backoff: suppress non-critical outbound traffic after
        # receiving user_rate_limited from the gateway.
        self._rate_limit_backoff_until = 0.0

    @property
    def device_key(self) -> str:
        return getattr(self, "_device_key", "") or ""

    @property
    def device_name(self) -> str:
        """Resolve device name dynamically from runtime config store."""
        from app.infrastructure.config.service import SystemConfigService

        return (
            SystemConfigService.get_value("EVOCLOUD_DEVICE_NAME")
            or self.config.device_name
            or platform.node()
            or "EvoLoop-Desktop"
        )

    @property
    def device_description(self) -> str:
        """Resolve device description dynamically from runtime config store."""
        from app.infrastructure.config.service import SystemConfigService

        return (
            SystemConfigService.get_value("EVOCLOUD_DEVICE_DESCRIPTION")
            or settings.EVOCLOUD_DEVICE_DESCRIPTION
            or ""
        )

    async def ensure_device_key(self) -> str:
        """Async initialization of device_key. Must be called before using device_key in async context."""
        if not getattr(self, "_device_key", ""):
            self._device_key = await self._get_or_create_device_key()
        return self._device_key

    async def _get_or_create_device_key(self) -> str:
        # 0. Explicit override for local/dev testing
        env_key = os.environ.get("EVOCLOUD_DEVICE_KEY", "").strip()
        if env_key:
            logger.info(
                f"[EvoCloud] Device key loaded from EVOCLOUD_DEVICE_KEY: {env_key[:20]}..."
            )
            await identity_service.store.save_device_key(env_key)
            return env_key

        # 1. Try cache-backed storage first (separate from token storage)
        dk = await identity_service.store.get_device_key()
        if dk:
            logger.info(f"[EvoCloud] Device key loaded from persistent storage: {dk[:20]}...")
            return dk

        # 2. Claim device from server (server-issued device_key)
        fingerprint = get_hardware_fingerprint()
        device_name = self.device_name or f"{platform.node()}"
        os_info = platform.platform()

        logger.info(f"[EvoCloud] Claiming device from server (fingerprint={fingerprint[:16]}...)")

        result = await self.api.register_device(fingerprint, device_name, os_info)
        if result and result.get("code") == 0:
            data = result.get("data", {})
            dk = data.get("device_key", "")
            is_new = data.get("is_new", True)
            if dk:
                await identity_service.store.save_device_key(dk)
                logger.info(
                    f"[EvoCloud] Device claimed successfully: {dk[:20]}... (is_new={is_new})"
                )
                return dk
            else:
                raise RuntimeError("Server returned empty device_key")
        else:
            msg = result.get("message", "unknown error") if result else "no response"
            raise RuntimeError(f"Device claim failed: {msg}")

    async def bind_client_id(self, client_id: str):
        """Bind a mobile client to this device via HTTP API."""
        dk = await self.ensure_device_key()
        if dk:
            await self.api.bind_client_id(dk, client_id)
        else:
            logger.warning("[EvoCloud] Cannot bind client: device_key not available")

    def is_connected(self) -> bool:
        if not self._running or self.ws is None:
            return False
        return self.ws.state == websockets.State.OPEN

    async def send_message(self, message: dict | str):
        """Send message to Cloud via WebSocket.

        If connection is down, enqueue the message for later retry.
        Only canonical envelopes should be sent; non-canonical messages are
        logged as warnings for debugging.
        """
        if isinstance(message, dict) and not is_canonical_envelope(message):
            logger.warning(
                f"[EvoCloud] send_message: non-canonical envelope type={message.get('type', 'unknown')}"
            )

        if self.is_connected() and self.ws:
            try:
                payload = message if isinstance(message, str) else json.dumps(message)
                logger.info(f"[EvoCloud] WS SEND RAW: {payload[:500]}...")
                await self.ws.send(payload)
                return True
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"[EvoCloud] WS Send Error: {e}, enqueueing for retry")
        else:
            logger.debug("[EvoCloud] WS not connected, enqueueing message for retry")

        # Enqueue for retry when connection is restored
        try:
            self._send_queue.put_nowait(message)
            logger.debug(
                f"[EvoCloud] Message enqueued for retry, queue_size={self._send_queue.qsize()}"
            )
            return False
        except asyncio.QueueFull:
            logger.warning("[EvoCloud] Send queue full, dropping message")
            return False

    async def start(self):
        """Start the WebSocket connection and Heartbeat Loops.

        Device registration is now server-issued. The device_key is obtained
        via HTTP claim before WebSocket connection.
        """
        if self._running:
            return

        if not await self.api.get_token():
            logger.warning("[EvoCloud] Cannot start Device Link: No Token")
            return

        dk = await self.ensure_device_key()
        if not dk:
            logger.error(
                "[EvoCloud] Cannot start Device Link: No valid device_key from server"
            )
            return

        self._running = True

        logger.info(
            f"[EvoCloud] Starting Device Link (device_key={self.device_key})..."
        )
        self._send_queue_task = asyncio.create_task(self._send_queue_loop())
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._ws_connect_loop())

    async def stop(self):
        self._running = False
        if self._send_queue_task:
            self._send_queue_task.cancel()
            try:
                await self._send_queue_task
            except asyncio.CancelledError:
                pass
        if self.ws:
            try:
                # Close with timeout to avoid hanging
                await asyncio.wait_for(self.ws.close(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.debug("[EvoCloud] WS close timed out, forcing disconnect")
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.debug(f"[EvoCloud] Error closing WS: {e}")
            finally:
                self.ws = None

    async def _send_queue_loop(self):
        """Background loop that drains the send queue when connection is available."""
        while self._running:
            try:
                # Wait for connection to be established
                if not self.is_connected():
                    await asyncio.sleep(1)
                    continue

                # Process messages from queue with timeout to allow periodic connection checks
                try:
                    message = await asyncio.wait_for(
                        self._send_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # Try to send
                try:
                    payload = (
                        message if isinstance(message, str) else json.dumps(message)
                    )
                    await self.ws.send(payload)
                    logger.info(f"[EvoCloud] WS SEND RETRY: {payload[:200]}")
                    self._send_queue.task_done()
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.warning(
                        f"[EvoCloud] WS retry send failed: {e}, re-enqueueing"
                    )
                    # Re-enqueue at the front for next retry
                    try:
                        # Put back at front using a temporary list (Queue doesn't support put_front)
                        # We'll just put it back at the end; order may shift slightly but all msgs will retry
                        self._send_queue.put_nowait(message)
                    except asyncio.QueueFull:
                        logger.warning(
                            "[EvoCloud] Send queue full during retry, dropping message"
                        )
                    self._send_queue.task_done()
            except asyncio.CancelledError:
                break
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"[EvoCloud] Send queue loop error: {e}")
                await asyncio.sleep(1)

    async def _heartbeat_loop(self):
        """Keep the connection and device heartbeat alive via two independent pings.

        Two separate mechanisms are required:

        1. **WebSocket control ping** (`ws.ping()`):
           Gateway calls SetPongHandler → SetReadDeadline(+60s) on each pong.
           Without this, the TCP connection is killed by the Gateway after 60 s
           of silence regardless of any JSON traffic.

        2. **JSON text ping** (`{"type": "ping"}`):
           Gateway's handleMessage routes this to deviceMgr.UpdateDeviceHeartbeat(),
           which keeps the device marked as "online" so A2A tasks are dispatched to it.
           The control-frame ping never reaches handleMessage, so it cannot substitute.

        Both must run every 30 s; removing either one breaks a different thing.
        """
        while self._running:
            if self.ws and self.is_connected():
                try:
                    # 发送控制层 ping，Gateway 收到后会回复 pong 并刷新读超时
                    await asyncio.wait_for(self.ws.ping(), timeout=10)
                except asyncio.TimeoutError:
                    logger.debug("[EvoCloud] WebSocket ping timed out, will reconnect")
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.debug(f"[EvoCloud] WebSocket ping failed: {e}")

                try:
                    # Also send JSON text ping to refresh deviceMgr heartbeat,
                    # but avoid aggravating the gateway while rate-limited.
                    if time.time() < self._rate_limit_backoff_until:
                        logger.debug(
                            "[EvoCloud] Skipping JSON text ping due to rate-limit backoff"
                        )
                    else:
                        ping_env = create_envelope(
                            type="ping",
                            body={"timestamp": int(time.time())},
                        )
                        await self.send_message(ping_env.model_dump())
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.debug(f"[EvoCloud] JSON text ping failed: {e}")
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
                logger.debug(
                    "[EvoCloud] SSL verification disabled for WebSocket (unverified context)"
                )
            else:
                # Use certifi to ensure we have valid CA certificates
                ssl_context = ssl.create_default_context(cafile=certifi.where())

        while self._running:
            try:
                # Ensure device key is loaded/created before each connection attempt
                await self.ensure_device_key()

                # Fetch token and append it to the WS URL for handshake authentication
                token = await self.api.get_token()
                ws_url = self.config.ws_url
                if token:
                    parsed = urlparse(ws_url)
                    query = parse_qs(parsed.query)
                    query["token"] = [token]
                    ws_url = urlunparse(
                        parsed._replace(query=urlencode(query, doseq=True))
                    )
                else:
                    logger.warning(
                        "[EvoCloud] No access token available; WS handshake will likely fail"
                    )

                logger.info(f"[EvoCloud) Connecting WS to {ws_url}...")

                async with websockets.connect(ws_url, ssl=ssl_context) as ws:
                    self.ws = ws
                    self._rate_limit_backoff_until = 0.0  # reset on new connection
                    logger.info("[EvoCloud] WS Connected. Sending handshake...")
                    self._handshake_completed = False

                    # New Go Gateway Handshake — 规范 Envelope 格式
                    from app.core.environment.discovery import EnvironmentProbe

                    handshake_body = {
                        "device_type": EnvironmentProbe.get_inferred_device_type(),
                        "device_key": self.device_key,
                        "device_name": self.device_name,
                                        "description": self.device_description,
                        "os_info": platform.platform(),
                    }
                    connect_env = create_envelope(
                        type="connect",
                        body=handshake_body,
                    )
                    await ws.send(connect_env.model_dump_json())

                    retry_count = 0  # Reset on success
                    async for message in ws:
                        await self._handle_ws_message(str(message))
            except ssl.SSLError as e:
                logger.error(f"[EvoCloud] SSL Certificate Error: {e}")
                if not self.config.ssl_verify:
                    logger.error(
                        "[EvoCloud] SSL verification is already disabled, but error persists"
                    )
                else:
                    logger.info(
                        "[EvoCloud] Tip: Set EVOCLOUD_SSL_VERIFY=false to disable SSL verification (development only)"
                    )
            except asyncio.CancelledError:
                raise  # Let cancellation propagate cleanly
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"[EvoCloud] WS Connection Error: {e}")
                if not self._handshake_completed and self.device_key:
                    logger.warning(
                        "[EvoCloud] Connection closed before handshake completed. Cached device key might be invalid. Clearing device key to force sync..."
                    )
                    await identity_service.store.delete_device_key()
                    self._device_key = ""
            finally:
                self.ws = None

            if self._running:
                # Exponential backoff
                delay = min(max_delay, base_delay * (2**retry_count))
                logger.info(f"[EvoCloud] Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                retry_count += 1

    # ------------------------------------------------------------------
    # Link-layer protocol handlers (infrastructure only, no business logic)
    # ------------------------------------------------------------------

    async def _on_command_relay_protocol(self, payload: dict) -> bool:
        """Send command_ack + deduplication. Returns False if duplicate."""
        cmd_id = payload.get("command_id")
        thread_id = payload.get("thread_id")

        # Ensure command_id is present for downstream consumers
        if cmd_id is None:
            payload["command_id"] = 0
            cmd_id = 0

        # Deduplication
        if cmd_id and cmd_id in self._processed_commands:
            logger.info(
                f"[EvoCloud] command.relay skipped (duplicate): cmd_id={cmd_id}"
            )
            return False
        if cmd_id:
            self._processed_commands.append(cmd_id)

        # Ack — canonical format only
        ack_env = create_envelope(
            type=MessageType.COMMAND_ACK,
            body={
                "command_id": cmd_id,
                "thread_id": thread_id,
                "status": "received",
            },
            source=None,
            target=None,
        )
        asyncio.create_task(self.send_message(ack_env.model_dump()))
        logger.info(f"[EvoCloud] command_ack sent: cmd_id={cmd_id}")
        return True

    async def _on_init_protocol(self, payload: dict) -> bool:
        """Update client_id from init handshake."""
        client_id = payload.get("client_id")
        if client_id:
            self.client_id = client_id
        self._handshake_completed = True
        return True

    async def _on_error_protocol(self, payload: dict) -> bool:
        """Handle error messages from Gateway (e.g. invalid_token, device_sync_failed)."""
        code = payload.get("code")
        message = payload.get("message")
        logger.warning(f"[EvoCloud] WS ERROR RECV: code={code}, message={message}")

        if code == "user_rate_limited":
            backoff = 30
            self._rate_limit_backoff_until = time.time() + backoff
            logger.warning(
                f"[EvoCloud] Rate limited by server, suppressing non-critical sends for {backoff}s"
            )
            return False

        if code == "invalid_token":
            logger.info("[EvoCloud] WS received invalid_token, triggering immediate token refresh...")
            current_token = await self.api.get_token()
            new_token = await self.api.refresh_access_token(failed_token=current_token)
            if not new_token:
                logger.warning("[EvoCloud] Token refresh failed (refresh_token expired), clearing session and stopping link...")
                from app.core.identity import identity_service
                await identity_service.logout()
                await self.stop()
            return False

        if code == "device_sync_failed":
            logger.warning("[EvoCloud] Device key rejected by server (revoked or belongs to another user), clearing and re-claiming...")
            from app.core.identity import identity_service
            await identity_service.store.delete_device_key()
            self._device_key = ""
            asyncio.create_task(self._force_reconnect())
            return False

        return True

    _LINK_LAYER_HANDLERS: dict[
        str, Callable[["EvoCloudWebSocketLink", dict], Awaitable[bool]]
    ] = {
        "command.relay": _on_command_relay_protocol,
        "system.init": _on_init_protocol,
        "system.error": _on_error_protocol,
    }

    async def _handle_ws_message(self, message: str):
        """
        Unified message entry-point. Zero if/elif business branching.
        Only canonical envelopes accepted; non-canonical messages are dropped.
        """
        logger.info(f"[EvoCloud] WS RECV: {message[:500]}")
        try:
            raw = json.loads(message)
            if not is_canonical_envelope(raw):
                logger.warning(
                    f"[EvoCloud] Non-canonical message dropped: type={raw.get('type', 'unknown')}"
                )
                return

            msg_type = raw.get("type", "unknown")
            body = raw.get("body", {})

            # Link-layer handlers (infrastructure only)
            handler = self._LINK_LAYER_HANDLERS.get(msg_type)
            if handler:
                should_publish = await handler(self, body)
                if not should_publish:
                    return

            if msg_type == "command.ack":
                logger.debug(
                    f"[EvoCloud] command.ack received: cmd_id={body.get('command_id')} status={body.get('status')}"
                )
                return

            from app.core.engine.event.publishers import publish_ws_message_received

            await publish_ws_message_received(
                msg_type=msg_type,
                payload=body,
                raw=raw,
            )

        except (json.JSONDecodeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[EvoCloud] WS Handle Error: {e}")

    def _on_token_changed(self, token: str | None):
        """Callback invoked when the access token changes. Triggers reconnect
        so the next handshake uses the latest token."""
        if not self._running or not self.ws or not token:
            return
        logger.info(
            "[EvoCloud] Token changed, triggering reconnect to use new token..."
        )
        try:
            asyncio.get_running_loop().create_task(self._force_reconnect())
        except RuntimeError:
            logger.debug("[EvoCloud] Token change reconnect skipped (no running loop)")

    async def _force_reconnect(self):
        """Force close current WebSocket connection to trigger reconnect.

        Used when a command times out or the connection is stuck,
        to let Gateway detect disconnect and clean up device status.
        """
        logger.warning(
            "[EvoCloud] Force reconnect triggered due to stuck command/timeout"
        )
        if self.ws:
            try:
                await self.ws.close()
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.debug(f"[EvoCloud] Error during force reconnect close: {e}")
        self.ws = None
