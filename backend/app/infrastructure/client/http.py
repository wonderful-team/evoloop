"""
HTTP Client Communication - Server-side HTTP proxy for Client tool execution.

When Agent needs to execute a local tool (file, shell, MCP), this proxy:
1. Creates a pending tool request
2. Waits for Client to poll via HTTP
3. Client executes and returns result via HTTP
4. Returns result to Agent

This is the fallback mechanism when WebSocket is not available.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.config import settings
from app.infrastructure.schemas import ToolRequest
from app.utils.id import gen_uuid_hex

logger = logging.getLogger(__name__)


class ToolRequestManager:
    """
    Manages pending tool requests for Client execution.
    Singleton pattern for global access.
    """

    _instance = None
    _lock = asyncio.Lock()
    _requests: dict[str, ToolRequest]
    _thread_requests: dict[str, list[str]]
    _cleanup_task: asyncio.Task | None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._requests = {}
            cls._instance._thread_requests = {}
            cls._instance._cleanup_task = None
        return cls._instance

    async def start(self):
        """Start the cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("ToolRequestManager started")

    async def stop(self):
        """Stop the cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def create_request(
        self, thread_id: str, tool: str, params: dict[str, Any]
    ) -> ToolRequest:
        """Create a new tool request."""
        request_id = f"tool-{gen_uuid_hex()[:12]}"
        request = ToolRequest(
            request_id=request_id,
            thread_id=thread_id,
            tool=tool,
            params=params,
        )

        async with self._lock:
            self._requests[request_id] = request
            if thread_id not in self._thread_requests:
                self._thread_requests[thread_id] = []
            self._thread_requests[thread_id].append(request_id)

        logger.info(f"[Client] Created tool request {request_id} for thread {thread_id}: {tool}")
        return request

    async def get_request(self, request_id: str) -> ToolRequest | None:
        """Get a request by ID."""
        async with self._lock:
            return self._requests.get(request_id)

    async def get_pending_for_thread(self, thread_id: str) -> list[ToolRequest]:
        """Get all pending requests for a thread."""
        async with self._lock:
            request_ids = self._thread_requests.get(thread_id, [])
            return [
                self._requests[rid] for rid in request_ids
                if self._requests[rid].status == "pending"
            ]

    async def get_all_pending(self) -> list[ToolRequest]:
        """Get all pending requests."""
        async with self._lock:
            return [req for req in self._requests.values() if req.status == "pending"]

    async def complete_request(self, request_id: str, result: Any, error: str | None = None) -> bool:
        """Mark a request as completed with result or error."""
        async with self._lock:
            request = self._requests.get(request_id)
            if not request:
                logger.warning(f"[Client] Request {request_id} not found for completion")
                return False

            request.status = "failed" if error else "completed"
            request.result = result
            request.error = error
            request.completed_at = datetime.utcnow()
            request.event.set()

        logger.info(f"[Client] Request {request_id} completed")
        return True

    async def wait_for_result(self, request_id: str, timeout: float = 300.0) -> ToolRequest | None:
        """Wait for a request to complete."""
        request = await self.get_request(request_id)
        if not request:
            return None

        try:
            await asyncio.wait_for(request.event.wait(), timeout=timeout)
            return request
        except asyncio.TimeoutError:
            logger.exception(f"[Client] Timeout waiting for request {request_id}")
            request.status = "failed"
            request.error = "Timeout waiting for tool execution"
            return request

    async def cancel_thread_requests(self, thread_id: str):
        """Cancel all pending requests for a thread."""
        async with self._lock:
            request_ids = self._thread_requests.get(thread_id, [])
            for rid in request_ids:
                req = self._requests.get(rid)
                if req and req.status == "pending":
                    req.status = "failed"
                    req.error = "Cancelled"
                    req.event.set()
            self._thread_requests[thread_id] = []

    async def _cleanup_loop(self):
        """Periodically clean up old completed requests."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                await self._cleanup_old_requests()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"[Client] Cleanup error: {e}")

    async def _cleanup_old_requests(self):
        """Remove completed requests older than 1 hour."""
        cutoff = datetime.utcnow() - timedelta(hours=1)
        async with self._lock:
            to_remove = [
                rid for rid, req in self._requests.items()
                if req.completed_at and req.completed_at < cutoff
            ]
            for rid in to_remove:
                req = self._requests.pop(rid, None)
                if req:
                    thread_id = req.thread_id
                    if thread_id in self._thread_requests:
                        self._thread_requests[thread_id] = [
                            r for r in self._thread_requests[thread_id]
                            if r != rid
                        ]


# Global instance
tool_request_manager = ToolRequestManager()


class ClientCapabilitiesManager:
    """
    Manages Client-reported capabilities for HTTP mode.

    In HTTP mode, Client reports its capabilities via REST API.
    This is a simpler alternative to WebSocket capability reporting.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = set()
            cls._instance._prefixes = set()
            cls._instance._version = ""
            cls._instance._last_reported = None
        return cls._instance

    def update_capabilities(
        self,
        tools: list[str],
        version: str = "1.0",
        patterns: dict[str, list[str]] | None = None,
    ):
        """Update Client capabilities."""
        self._tools = set(tools)
        if patterns:
            self._prefixes = set(patterns.get("prefixes", []))
        self._version = version
        self._last_reported = datetime.utcnow()
        logger.info(f"[HTTP Capabilities] Updated: {len(tools)} tools, {len(self._prefixes)} prefixes, version {version}")

    def supports_tool(self, tool_name: str) -> bool:
        """Check if Client supports a specific tool."""
        if not self._tools and not self._prefixes:
            # No capabilities reported yet, assume support for common tools
            return True

        # Check exact match
        if tool_name in self._tools:
            return True

        # Check prefix patterns (e.g., "adb_", "browser_", "desktop_")
        for prefix in self._prefixes:
            if tool_name.startswith(prefix):
                return True

        # Check for MCP tools (mcp__server__tool format)
        if tool_name.startswith("mcp__"):
            return True

        return False

    def get_supported_tools(self) -> set[str]:
        """Get the set of supported tools."""
        return self._tools.copy()

    def get_prefixes(self) -> set[str]:
        """Get the set of supported tool prefixes."""
        return self._prefixes.copy()

    def is_reported(self) -> bool:
        """Check if capabilities have been reported."""
        return self._last_reported is not None


# Global instance for HTTP mode capabilities
client_capabilities = ClientCapabilitiesManager()


class ClientToolExecutor:
    """
    Executes tools through the Client (Python sidecar process).

    This is used by the Agent when it needs to execute a local tool.
    The execution flow:
    1. Create a pending tool request
    2. Wait for Client to poll and execute
    3. Return result to Agent
    """

    def __init__(self, client_callback_url: str | None = None):
        self.client_callback_url = client_callback_url or settings.CLIENT_CALLBACK_URL
        self._http_client = httpx.AsyncClient(timeout=30.0)

    async def execute(
        self,
        thread_id: str,
        tool: str,
        params: dict[str, Any],
        timeout: float = 300.0
    ) -> Any:
        """
        Execute a tool through Client.

        Args:
            thread_id: The conversation thread ID
            tool: Tool name (file_read, file_write, shell, mcp, etc.)
            params: Tool parameters
            timeout: Maximum time to wait for execution

        Returns:
            Tool execution result

        Raises:
            ToolExecutionError: If execution fails or times out
        """
        # 1. Create pending request
        request = await tool_request_manager.create_request(
            thread_id=thread_id,
            tool=tool,
            params=params
        )

        # 2. Wait for result (Client will poll via HTTP)
        completed = await tool_request_manager.wait_for_result(
            request.request_id,
            timeout=timeout
        )

        if not completed:
            raise ToolExecutionError(f"Request {request.request_id} disappeared")

        if completed.error:
            raise ToolExecutionError(completed.error)

        return completed.result

    async def close(self):
        """Close HTTP client."""
        await self._http_client.aclose()


class ToolExecutionError(Exception):
    """Error executing tool through Client."""

    pass


# Convenience function for Agent
def get_client_executor() -> ClientToolExecutor:
    """Get the Client tool executor instance."""
    return ClientToolExecutor()
