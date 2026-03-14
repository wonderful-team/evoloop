"""
Event handlers for Sidecar protocol.

Events are sent from Client to Tauri (not the other way around).
This module provides helper functions to send various events.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class EventPublisher:
    """Helper to publish events to Tauri via stdout."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._protocol = None
        return cls._instance

    def set_protocol(self, protocol):
        """Set the protocol instance to use for sending events."""
        self._protocol = protocol

    async def _send(self, event_type: str, data: Dict[str, Any]) -> None:
        """Send an event to Tauri."""
        if self._protocol:
            await self._protocol.send_event(event_type, data)
        else:
            logger.warning(f"No protocol set, event dropped: {event_type}")

    # File system events
    async def file_changed(self, path: str, change_type: str = "modified") -> None:
        """Notify that a file has changed."""
        await self._send("file_changed", {
            "path": path,
            "type": change_type,  # created, modified, deleted, moved
        })

    async def indexing_progress(self, repo_id: str, progress: float, status: str) -> None:
        """Report indexing progress."""
        await self._send("indexing_progress", {
            "repo_id": repo_id,
            "progress": progress,
            "status": status,
        })

    # MCP events
    async def mcp_connected(self, server_name: str) -> None:
        """Notify that an MCP server connected."""
        await self._send("mcp_connected", {"server": server_name})

    async def mcp_disconnected(self, server_name: str, reason: str = "") -> None:
        """Notify that an MCP server disconnected."""
        await self._send("mcp_disconnected", {
            "server": server_name,
            "reason": reason,
        })

    # Environment events
    async def device_connected(self, device_id: str, device_type: str) -> None:
        """Notify that a device (Android, etc) connected."""
        await self._send("device_connected", {
            "device_id": device_id,
            "device_type": device_type,
        })

    async def device_disconnected(self, device_id: str) -> None:
        """Notify that a device disconnected."""
        await self._send("device_disconnected", {"device_id": device_id})

    # Error events
    async def error(self, error_type: str, message: str, details: Optional[Dict] = None) -> None:
        """Report an error."""
        await self._send("error", {
            "error_type": error_type,
            "message": message,
            "details": details or {},
        })

    # Log events (for remote debugging)
    async def log(self, level: str, message: str, source: str = "client") -> None:
        """Send a log message."""
        await self._send("log", {
            "level": level,
            "message": message,
            "source": source,
            "timestamp": asyncio.get_event_loop().time(),
        })

    # Activity/Step events
    async def step_create(self, thread_id: str, step_id: int, name: str, step_type: str = "node") -> None:
        """Notify that a new step has started."""
        await self._send("step_create", {
            "thread_id": thread_id,
            "step_id": step_id,
            "name": name,
            "type": step_type,
            "status": "running",
        })

    async def step_update(self, thread_id: str, step_id: int, status: str, details: str = None) -> None:
        """Notify that a step has been updated."""
        data = {
            "thread_id": thread_id,
            "step_id": step_id,
            "status": status,
        }
        if details:
            data["details"] = details
        await self._send("step_update", data)

    # HITL events
    async def hitl_response(self, thread_id: str, response: str, command_id: str = None) -> None:
        """Forward HITL response to Tauri."""
        await self._send("hitl_response", {
            "thread_id": thread_id,
            "response": response,
            "command_id": command_id,
        })

    async def chat_message(self, thread_id: str, message: str, attachments: list = None, project_id: int = None, command_id: str = None) -> None:
        """Forward chat message to Tauri."""
        await self._send("chat_message", {
            "thread_id": thread_id,
            "message": message,
            "attachments": attachments or [],
            "project_id": project_id,
            "command_id": command_id,
        })

    async def remote_command(self, command_type: str, data: dict) -> None:
        """Forward remote command to Tauri."""
        await self._send("remote_command", {
            "command_type": command_type,
            "data": data,
        })


# Global event publisher
events = EventPublisher()


def setup_event_forwarding():
    """
    Set up forwarding of internal events to the Sidecar protocol.

    This bridges the existing event system with the Sidecar stdout protocol.
    """
    from app.sidecar.protocol import get_protocol

    # Set the protocol for event publishing
    events.set_protocol(get_protocol())

    logger.info("Event forwarding to Sidecar protocol configured")
