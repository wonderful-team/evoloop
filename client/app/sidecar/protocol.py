"""
Sidecar Protocol - JSON Lines communication with Tauri.

Tauri <-> Client communication via stdin/stdout using JSON Lines format.
Each line is a JSON message.
"""

import asyncio
import json
import logging
import sys
from typing import Callable, Dict, Any, Optional

logger = logging.getLogger(__name__)


class SidecarProtocol:
    """Handles JSON Lines protocol over stdin/stdout."""

    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._running = False
        self._stdin_reader = None

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        self._handlers[message_type] = handler
        logger.debug(f"Registered handler for {message_type}")

    async def start(self) -> None:
        """Start the protocol loop."""
        self._running = True
        logger.info("Sidecar protocol started, listening on stdin...")

        # Use asyncio.StreamReader for stdin
        loop = asyncio.get_event_loop()
        self._stdin_reader = asyncio.StreamReader()
        await loop.connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(self._stdin_reader),
            sys.stdin
        )

        try:
            while self._running:
                try:
                    line = await self._stdin_reader.readline()
                    if not line:
                        # EOF - stdin closed
                        logger.info("stdin closed, shutting down...")
                        break

                    line = line.decode('utf-8').strip()
                    if not line:
                        continue

                    await self._handle_message(line)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error reading from stdin: {e}")
                    await self.send_response({
                        "type": "error",
                        "error": f"Protocol error: {str(e)}"
                    })

        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the protocol loop."""
        self._running = False
        logger.info("Sidecar protocol stopped")

    async def _handle_message(self, line: str) -> None:
        """Parse and route incoming message."""
        try:
            message = json.loads(line)
            msg_type = message.get("type")
            msg_id = message.get("id")

            logger.debug(f"Received {msg_type} message (id={msg_id})")

            if msg_type in self._handlers:
                try:
                    result = await self._handlers[msg_type](message)
                    # Send result if request has an id
                    if msg_id and result is not None:
                        await self.send_response({
                            "type": "result",
                            "id": msg_id,
                            **result
                        })
                except Exception as e:
                    logger.error(f"Handler error for {msg_type}: {e}", exc_info=True)
                    if msg_id:
                        await self.send_response({
                            "type": "error",
                            "id": msg_id,
                            "error": str(e)
                        })
            else:
                logger.warning(f"No handler for message type: {msg_type}")
                if msg_id:
                    await self.send_response({
                        "type": "error",
                        "id": msg_id,
                        "error": f"Unknown message type: {msg_type}"
                    })

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {line[:100]}...")
            await self.send_response({
                "type": "error",
                "error": f"Invalid JSON: {str(e)}"
            })

    async def send_response(self, data: Dict[str, Any]) -> None:
        """Send a response to stdout."""
        try:
            line = json.dumps(data, ensure_ascii=False)
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
            logger.debug(f"Sent: {line[:200]}...")
        except Exception as e:
            logger.error(f"Failed to send response: {e}")

    async def send_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Send an event to Tauri (no response expected)."""
        await self.send_response({
            "type": "event",
            "event": event_type,
            **data
        })


# Global protocol instance
_protocol: Optional[SidecarProtocol] = None


def get_protocol() -> SidecarProtocol:
    """Get the global protocol instance."""
    global _protocol
    if _protocol is None:
        _protocol = SidecarProtocol()
    return _protocol


def send_event_sync(event_type: str, **kwargs) -> None:
    """Synchronous helper to send events from non-async contexts."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(get_protocol().send_event(event_type, kwargs))
        else:
            loop.run_until_complete(get_protocol().send_event(event_type, kwargs))
    except Exception as e:
        logger.error(f"Failed to send event: {e}")
