"""
Heartbeat Manager for EvoLoop Cloud Connection.

Maintains connection health through:
- Periodic heartbeat pings
- Automatic reconnection
- Connection state monitoring
- Graceful degradation on disconnection
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Callable, Optional

from app.core.config import settings
from app.infrastructure.cloud import CloudClient
from app.logging import logger


class ConnectionState(Enum):
    """Connection state machine."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    ERROR = auto()


@dataclass
class ConnectionStats:
    """Connection statistics."""
    state: ConnectionState
    last_heartbeat: Optional[datetime]
    last_successful_heartbeat: Optional[datetime]
    heartbeat_failures: int
    total_heartbeats: int
    reconnections: int
    connected_since: Optional[datetime]


class HeartbeatManager:
    """
    Manages cloud connection heartbeat.

    Features:
    - Periodic heartbeat (default 30s)
    - Automatic reconnection with exponential backoff
    - Connection state callbacks
    - Graceful shutdown
    """

    def __init__(
        self,
        client: CloudClient = None,
        interval: float = 30.0,
        timeout: float = 10.0,
        max_failures: int = 3,
    ):
        self.client = client
        self.interval = interval
        self.timeout = timeout
        self.max_failures = max_failures

        # State
        self._state = ConnectionState.DISCONNECTED
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        # Stats
        self._stats = ConnectionStats(
            state=ConnectionState.DISCONNECTED,
            last_heartbeat=None,
            last_successful_heartbeat=None,
            heartbeat_failures=0,
            total_heartbeats=0,
            reconnections=0,
            connected_since=None,
        )

        # Callbacks
        self._on_state_change: list[Callable[[ConnectionState, ConnectionState], None]] = []
        self._on_heartbeat_success: list[Callable[[], None]] = []
        self._on_heartbeat_failure: list[Callable[[int], None]] = []
        self._on_disconnect: list[Callable[[], None]] = []

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._state == ConnectionState.CONNECTED

    @property
    def stats(self) -> ConnectionStats:
        """Get connection statistics."""
        return self._stats

    def on_state_change(self, callback: Callable[[ConnectionState, ConnectionState], None]):
        """Register callback for state changes."""
        self._on_state_change.append(callback)

    def on_heartbeat_success(self, callback: Callable[[], None]):
        """Register callback for successful heartbeat."""
        self._on_heartbeat_success.append(callback)

    def on_heartbeat_failure(self, callback: Callable[[int], None]):
        """Register callback for heartbeat failure."""
        self._on_heartbeat_failure.append(callback)

    def on_disconnect(self, callback: Callable[[], None]):
        """Register callback for disconnection."""
        self._on_disconnect.append(callback)

    async def start(self):
        """Start heartbeat manager."""
        if self._task is not None:
            logger.warning("[HeartbeatManager] Already started")
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info("[HeartbeatManager] Started")

    async def stop(self):
        """Stop heartbeat manager."""
        if self._task is None:
            return

        self._stop_event.set()
        self._task.cancel()

        try:
            await self._task
        except asyncio.CancelledError:
            pass

        self._task = None

        # Update state
        old_state = self._state
        self._state = ConnectionState.DISCONNECTED
        self._notify_state_change(old_state, self._state)

        logger.info("[HeartbeatManager] Stopped")

    async def _heartbeat_loop(self):
        """Main heartbeat loop."""
        while not self._stop_event.is_set():
            try:
                # Ensure client
                if self.client is None:
                    from app.infrastructure.cloud import get_cloud_client
                    self.client = get_cloud_client()
                    await self.client.connect()

                # Connect WebSocket if not connected
                if not self.client._ws_connected:
                    await self._connect_websocket()

                # Send heartbeat
                await self._send_heartbeat()

                # Wait for next interval
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.interval
                )

            except asyncio.TimeoutError:
                # Normal interval timeout, continue loop
                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[HeartbeatManager] Loop error: {e}")
                await asyncio.sleep(1)

    async def _connect_websocket(self):
        """Connect WebSocket with state updates."""
        old_state = self._state
        self._state = ConnectionState.CONNECTING
        self._notify_state_change(old_state, self._state)

        try:
            await self.client.connect_websocket()

            old_state = self._state
            self._state = ConnectionState.CONNECTED
            self._stats.connected_since = datetime.utcnow()
            self._notify_state_change(old_state, self._state)

            logger.info("[HeartbeatManager] WebSocket connected")

        except Exception as e:
            logger.error(f"[HeartbeatManager] Connection failed: {e}")

            old_state = self._state
            self._state = ConnectionState.ERROR
            self._notify_state_change(old_state, self._state)

            # Trigger reconnection
            await self._reconnect()

    async def _send_heartbeat(self):
        """Send heartbeat ping."""
        from app.infrastructure.cloud.protocol import CloudMessage

        self._stats.last_heartbeat = datetime.utcnow()
        self._stats.total_heartbeats += 1

        try:
            message = CloudMessage.heartbeat(
                device_id=self.client.config.device_id or "unknown",
                status="online" if self.is_connected else "degraded"
            )

            # Send via WebSocket with timeout
            response = await asyncio.wait_for(
                self.client.send_ws_message(message, wait_for_response=True),
                timeout=self.timeout
            )

            if response and response.msg_type.value == "heartbeat_ack":
                # Success
                self._stats.last_successful_heartbeat = datetime.utcnow()
                self._stats.heartbeat_failures = 0

                for callback in self._on_heartbeat_success:
                    try:
                        callback()
                    except Exception as e:
                        logger.error(f"[HeartbeatManager] Success callback error: {e}")

                logger.debug("[HeartbeatManager] Heartbeat acknowledged")
            else:
                await self._handle_heartbeat_failure()

        except asyncio.TimeoutError:
            logger.warning("[HeartbeatManager] Heartbeat timeout")
            await self._handle_heartbeat_failure()
        except Exception as e:
            logger.error(f"[HeartbeatManager] Heartbeat error: {e}")
            await self._handle_heartbeat_failure()

    async def _handle_heartbeat_failure(self):
        """Handle heartbeat failure."""
        self._stats.heartbeat_failures += 1

        for callback in self._on_heartbeat_failure:
            try:
                callback(self._stats.heartbeat_failures)
            except Exception as e:
                logger.error(f"[HeartbeatManager] Failure callback error: {e}")

        if self._stats.heartbeat_failures >= self.max_failures:
            logger.error(f"[HeartbeatManager] Max failures reached ({self.max_failures}), reconnecting...")
            await self._reconnect()

    async def _reconnect(self):
        """Attempt reconnection with exponential backoff."""
        old_state = self._state
        self._state = ConnectionState.RECONNECTING
        self._notify_state_change(old_state, self._state)

        # Close existing connection
        if self.client:
            await self.client.close()

        # Exponential backoff
        for attempt in range(5):  # Max 5 attempts
            if self._stop_event.is_set():
                break

            delay = min(2 ** attempt, 60)  # Max 60s delay
            logger.info(f"[HeartbeatManager] Reconnect attempt {attempt + 1} in {delay}s...")
            await asyncio.sleep(delay)

            try:
                # Reconnect
                from app.infrastructure.cloud import get_cloud_client
                self.client = get_cloud_client()
                await self.client.connect()
                await self.client.connect_websocket()

                # Success
                self._stats.reconnections += 1
                self._stats.heartbeat_failures = 0

                old_state = self._state
                self._state = ConnectionState.CONNECTED
                self._stats.connected_since = datetime.utcnow()
                self._notify_state_change(old_state, self._state)

                logger.info("[HeartbeatManager] Reconnected successfully")
                return

            except Exception as e:
                logger.error(f"[HeartbeatManager] Reconnect attempt {attempt + 1} failed: {e}")

        # All attempts failed
        old_state = self._state
        self._state = ConnectionState.ERROR
        self._notify_state_change(old_state, self._state)

        for callback in self._on_disconnect:
            try:
                callback()
            except Exception as e:
                logger.error(f"[HeartbeatManager] Disconnect callback error: {e}")

        logger.error("[HeartbeatManager] All reconnection attempts failed")

    def _notify_state_change(self, old_state: ConnectionState, new_state: ConnectionState):
        """Notify state change callbacks."""
        self._stats.state = new_state

        for callback in self._on_state_change:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.error(f"[HeartbeatManager] State change callback error: {e}")


# Global instance
_heartbeat_manager: Optional[HeartbeatManager] = None


def get_heartbeat_manager() -> HeartbeatManager:
    """Get global heartbeat manager instance."""
    global _heartbeat_manager
    if _heartbeat_manager is None:
        _heartbeat_manager = HeartbeatManager()
    return _heartbeat_manager


async def start_cloud_connection():
    """Start cloud connection with heartbeat."""
    manager = get_heartbeat_manager()
    await manager.start()
    return manager


async def stop_cloud_connection():
    """Stop cloud connection."""
    global _heartbeat_manager
    if _heartbeat_manager:
        await _heartbeat_manager.stop()
        _heartbeat_manager = None
