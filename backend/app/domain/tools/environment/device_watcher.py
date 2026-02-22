"""
Device Watcher - Monitors ADB device connection events.
"""

import asyncio
import logging

from app.domain.tools.environment.mirror_session import mirror_manager
from app.infrastructure.drivers.adb import adb_driver

logger = logging.getLogger(__name__)


class DeviceWatcher:
    """
    Background service that tracks ADB device status changes.
    """
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self):
        """Start the background watcher task."""
        if not self._task:
            self._running = True
            self._task = asyncio.create_task(self._watch_loop())
            logger.info("DeviceWatcher started")

    def stop(self):
        """Stop the background watcher task."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("DeviceWatcher stopped")

    async def _watch_loop(self):
        """
        Listen to 'adb track-devices' output.
        Each update from 'adb track-devices' is the ENTIRE list of devices.
        """
        last_devices = set()

        while self._running:
            try:
                logger.info("Restarting 'adb track-devices' process...")
                process = await asyncio.create_subprocess_exec(
                    adb_driver._adb_path, "track-devices",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                while self._running:
                    # ADB sends the whole list in one go. We need to read lines.
                    # 'adb track-devices' is stream-oriented.
                    line = await process.stdout.readline()
                    if not line:
                        logger.warning("adb track-devices connection lost")
                        break

                    decoded_line = line.decode().strip()
                    if not decoded_line:
                        # Empty list or end of block?
                        # ADB track-devices sends an empty line if no devices.
                        # We should handle the 'no devices' case.
                        current_serial = None
                        current_status = None
                    else:
                        # Strip length prefix if present
                        if len(decoded_line) > 4 and all(c in "0123456789abcdefABCDEF" for c in decoded_line[:4]):
                            decoded_line = decoded_line[4:].strip()

                        parts = decoded_line.split()
                        if len(parts) >= 2:
                            current_serial = parts[0]
                            current_status = parts[1]
                        else:
                            current_serial = None
                            current_status = None

                    # Note: Simplified detection. In complex environments with many devices,
                    # we'd want to buffer the whole 'block' sent by track-devices.
                    # But for 1-2 devices, immediate action is okay.
                    if current_serial:
                        if current_status == "device":
                            if current_serial not in last_devices:
                                logger.info(f"New device detected: {current_serial}")
                                await self._handle_event(current_serial, "device")
                                last_devices.add(current_serial)
                        elif current_status in ["offline", "unauthorized"]:
                            if current_serial in last_devices:
                                logger.info(f"Device went {current_status}: {current_serial}")
                                await self._handle_event(current_serial, current_status)
                                last_devices.discard(current_serial)

                    # Heartbeat
                    if last_devices:
                        logger.debug(f"DeviceWatcher heartbeat - active: {last_devices}")

                # Cleanup on exit
                if process.returncode is None:
                    process.terminate()
                await process.wait()
                await asyncio.sleep(2)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"DeviceWatcher error: {e}")
                await asyncio.sleep(5)

    async def _handle_event(self, serial: str, status: str):
        """Handle individual device events via event bus."""
        from app.core.environment.events import (
            DeviceConnectedEvent,
            DeviceDisconnectedEvent,
            event_bus,
        )

        if status == "device":
            logger.info(f"Device connected: {serial}")
            # Try to recover sessions marked as 'should_be_active'
            await mirror_manager.on_device_connected(serial)

            # Publish device connected event (handlers will refresh state and probe)
            await event_bus.publish(DeviceConnectedEvent(
                device_id=serial,
                device_type="android"
            ))
            logger.info(f"🌅 Published device connected event: {serial}")
        else:
            logger.info(f"Device disconnected/offline: {serial} ({status})")
            # Cleanup sessions for this device
            mirror_manager.on_device_disconnected(serial)

            # Publish device disconnected event
            await event_bus.publish(DeviceDisconnectedEvent(device_id=serial))


# Global Watcher Instance
device_watcher = DeviceWatcher()
