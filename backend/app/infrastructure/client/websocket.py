"""
WebSocket Client Communication - Direct Client communication via WebSocket.

Provides a WebSocket server that accepts connections from Client
for direct tool execution.

Flow:
  Backend (WebSocket Server) ◄──── Client (WebSocket Client)
       │                                          │
       │──── execute_tool ───────────────────────►│
       │◄─── execute_result ──────────────────────│
"""

import asyncio
import json
import logging
import platform
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed

from app.core.config import settings

try:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False

logger = logging.getLogger(__name__)


@dataclass
class PendingToolRequest:
    """Represents a pending tool request awaiting response."""
    request_id: str
    thread_id: str
    tool: str
    params: dict[str, Any]
    future: asyncio.Future = field(default_factory=lambda: asyncio.get_event_loop().create_future())
    created_at: datetime = field(default_factory=datetime.utcnow)


class ClientWebSocketManager:
    """
    Manages WebSocket connections from Client for tool execution.

    Backend acts as WebSocket server, Client connects to it.
    This allows Backend to directly send tool requests to Client.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._websocket: Optional[websockets.WebSocketServerProtocol] = None
        self._pending_requests: dict[str, PendingToolRequest] = {}
        self._lock = asyncio.Lock()
        self._server = None
        self._is_running = False
        self._zeroconf: Optional[Any] = None
        self._service_info: Optional[Any] = None

        # Connection state
        self._client_connected = False
        self._client_id: Optional[str] = None

        # Client capabilities (reported by client)
        self._client_tools: set[str] = set()  # Exact tool names supported by connected client
        self._client_tool_prefixes: set[str] = set()  # Prefix patterns (e.g., "adb_", "browser_")

    async def start(self, host: str = "0.0.0.0", port: int = 8766):
        """
        Start the WebSocket server.

        Backend acts as WebSocket server, Client connects to it.
        """
        if self._is_running:
            return

        self._is_running = True

        async def handler(websocket, path):
            await self._handle_connection(websocket)

        self._server = await websockets.serve(
            handler,
            host,
            port,
            ping_interval=20,
            ping_timeout=10,
        )

        logger.info(f"[WebSocket] Tool server started on ws://{host}:{port}")

        # Start mDNS advertisement
        if HAS_ZEROCONF:
            try:
                self._zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
                desc = {'description': 'EvoLoop Desktop Agent'}

                import socket
                local_ip = socket.gethostbyname(socket.gethostname())
                # Fallback for some systems
                if local_ip == "127.0.0.1":
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    try:
                        s.connect(("8.8.8.8", 80))
                        local_ip = s.getsockname()[0]
                    finally:
                        s.close()

                self._service_info = ServiceInfo(
                    "_evoloop._tcp.local.",
                    f"{settings.EVOCLOUD_DEVICE_NAME or platform.node()}._evoloop._tcp.local.",
                    addresses=[socket.inet_aton(local_ip)],
                    port=port,
                    properties=desc,
                )
                self._zeroconf.register_service(self._service_info)
                logger.info(f"[mDNS] Registered service: {self._service_info.name} at {local_ip}:{port}")
            except Exception as e:
                logger.warning(f"[mDNS] Failed to register service: {e}")
        else:
            logger.info("[mDNS] Zeroconf not installed, local discovery disabled.")

    async def stop(self):
        """Stop the WebSocket server."""
        self._is_running = False

        # Cancel all pending requests
        async with self._lock:
            for req in self._pending_requests.values():
                if not req.future.done():
                    req.future.set_exception(ConnectionError("WebSocket server shutting down"))
            self._pending_requests.clear()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Stop mDNS
        if self._zeroconf:
            try:
                self._zeroconf.unregister_service(self._service_info)
                self._zeroconf.close()
                self._zeroconf = None
                logger.info("[mDNS] Unregistered service")
            except Exception as e:
                logger.warning(f"[mDNS] Failed to unregister service: {e}")

        logger.info("[WebSocket] Tool server stopped")

    async def _handle_connection(self, websocket: websockets.WebSocketServerProtocol):
        """Handle a new WebSocket connection from Client."""
        client_addr = websocket.remote_address
        logger.info(f"[WebSocket] Client connected from {client_addr}")

        # Only accept one client connection at a time
        if self._client_connected:
            logger.warning("[WebSocket] Rejecting additional client connection")
            await websocket.close(1013, "Only one client allowed")  # Try again later
            return

        self._websocket = websocket
        self._client_connected = True

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"[WebSocket] Invalid JSON: {e}")
                except Exception as e:
                    logger.error(f"[WebSocket] Error handling message: {e}")

        except ConnectionClosed:
            logger.info("[WebSocket] Client disconnected")
        finally:
            self._websocket = None
            self._client_connected = False
            self._client_tools.clear()  # Clear capabilities on disconnect
            self._client_tool_prefixes.clear()

    async def _handle_message(self, data: dict[str, Any]):
        """Handle incoming message from Client."""
        msg_type = data.get("type")

        if msg_type == "execute_result":
            # Client is returning a tool execution result
            await self._handle_execute_result(data)

        elif msg_type == "client_identify":
            # Client identification
            self._client_id = data.get("client_id")
            token = data.get("token")
            logger.info(f"[WebSocket] Client identified: {self._client_id}")

            # Send acknowledgment
            if self._websocket:
                await self._websocket.send(json.dumps({
                    "type": "identify_ack",
                    "client_id": self._client_id
                }))

        elif msg_type == "pong":
            # Keep-alive response
            pass

        elif msg_type == "status_response":
            # Status report from client
            logger.debug(f"[WebSocket] Client status: {data.get('status')}")

        elif msg_type == "client_capabilities":
            # Client reports its supported tools/capabilities
            tools = data.get("tools", [])
            patterns = data.get("patterns", {})

            self._client_tools = set(tools)
            self._client_tool_prefixes = set(patterns.get("prefixes", []))

            logger.info(f"[WebSocket] Client capabilities received: {len(tools)} tools")
            logger.debug(f"[WebSocket] Exact tools: {sorted(self._client_tools)}")
            logger.debug(f"[WebSocket] Prefix patterns: {sorted(self._client_tool_prefixes)}")

            # Send acknowledgment
            if self._websocket:
                await self._websocket.send(json.dumps({
                    "type": "capabilities_ack",
                    "tools_count": len(tools),
                    "patterns_count": len(self._client_tool_prefixes)
                }))

        else:
            logger.warning(f"[WebSocket] Unknown message type: {msg_type}")

    async def _handle_execute_result(self, data: dict[str, Any]):
        """Handle tool execution result from Client."""
        request_id = data.get("request_id")
        result = data.get("result")
        error = data.get("error")

        async with self._lock:
            pending = self._pending_requests.pop(request_id, None)

        if pending:
            if error:
                pending.future.set_exception(Exception(error))
            else:
                pending.future.set_result(result)
            logger.debug(f"[WebSocket] Request {request_id} completed")
        else:
            logger.warning(f"[WebSocket] Received result for unknown request: {request_id}")

    async def execute_tool(
        self,
        thread_id: str,
        tool: str,
        params: dict[str, Any],
        timeout: float = 300.0
    ) -> Any:
        """
        Execute a tool via WebSocket.

        Sends execute_tool message to Client and waits for response.
        """
        if not self._client_connected or not self._websocket:
            raise ConnectionError("Client not connected via WebSocket")

        request_id = f"ws-{asyncio.get_event_loop().time():.6f}"
        pending = PendingToolRequest(
            request_id=request_id,
            thread_id=thread_id,
            tool=tool,
            params=params
        )

        async with self._lock:
            self._pending_requests[request_id] = pending

        try:
            # Send tool request to Client
            message = {
                "type": "execute_tool",
                "request_id": request_id,
                "thread_id": thread_id,
                "tool": tool,
                "params": params
            }

            await self._websocket.send(json.dumps(message))
            logger.debug(f"[WebSocket] Sent tool request: {request_id} ({tool})")

            # Wait for result with timeout
            return await asyncio.wait_for(pending.future, timeout=timeout)

        except asyncio.TimeoutError:
            async with self._lock:
                self._pending_requests.pop(request_id, None)
            raise TimeoutError(f"Tool execution timed out after {timeout}s")

        except Exception as e:
            async with self._lock:
                self._pending_requests.pop(request_id, None)
            raise

    def is_connected(self) -> bool:
        """Check if Client is connected via WebSocket."""
        return self._client_connected and self._websocket is not None

    def supports_tool(self, tool_name: str) -> bool:
        """Check if connected Client supports a specific tool."""
        if not self._client_connected:
            return False

        # If no capabilities reported yet, assume support during transition
        if not self._client_tools and not self._client_tool_prefixes:
            return True

        # Check exact match first
        if tool_name in self._client_tools:
            return True

        # Check prefix patterns (e.g., "adb_", "browser_", "desktop_")
        for prefix in self._client_tool_prefixes:
            if tool_name.startswith(prefix):
                return True

        # Check for MCP tools (mcp__server__tool format)
        if tool_name.startswith("mcp__"):
            return True

        return False

    def get_supported_tools(self) -> set[str]:
        """Get the set of tools supported by the connected client."""
        return self._client_tools.copy()


# Global instance
client_ws_manager = ClientWebSocketManager()


class DirectClientToolExecutor:
    """
    Tool executor that directly communicates with Client via WebSocket.

    Falls back to HTTP if WebSocket is not connected.
    """

    def __init__(self):
        self._ws_manager = client_ws_manager
        self._http_fallback: Optional[Any] = None

    async def execute(
        self,
        thread_id: str,
        tool: str,
        params: dict[str, Any],
        timeout: float = 300.0
    ) -> Any:
        """
        Execute tool via WebSocket with HTTP fallback.
        """
        if self._ws_manager.is_connected():
            try:
                return await self._ws_manager.execute_tool(
                    thread_id=thread_id,
                    tool=tool,
                    params=params,
                    timeout=timeout
                )
            except Exception as e:
                logger.warning(f"[WebSocket] Failed, falling back to HTTP: {e}")
                # Fall through to HTTP

        # Fallback to HTTP
        return await self._http_execute(thread_id, tool, params, timeout)

    async def _http_execute(
        self,
        thread_id: str,
        tool: str,
        params: dict[str, Any],
        timeout: float
    ) -> Any:
        """HTTP fallback using ClientToolExecutor."""
        from app.infrastructure.client.http import ClientToolExecutor, ToolExecutionError

        if self._http_fallback is None:
            self._http_fallback = ClientToolExecutor()

        return await self._http_fallback.execute(thread_id, tool, params, timeout)


def get_direct_client_executor() -> DirectClientToolExecutor:
    """Get the direct client tool executor instance."""
    return DirectClientToolExecutor()
