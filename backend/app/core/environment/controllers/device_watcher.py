"""
Device Watcher — Monitors ADB device connection events.
"""

import asyncio
import logging

from app.core.config import settings
from app.core.environment.controllers.mirror_session import mirror_manager
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
        if not settings.ENABLE_ENVIRONMENT_CONTROLS:
            logger.info("Environment controls disabled, skipping DeviceWatcher")
            return

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
                    adb_driver._adb_path,
                    "track-devices",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                while self._running:
                    line = await process.stdout.readline()
                    if not line:
                        logger.warning("adb track-devices connection lost")
                        break

                    decoded_line = line.decode().strip()
                    if not decoded_line:
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

        if status == "device":
            logger.info(f"Device connected: {serial}")

            # Detect device capabilities (uiautomator vs uiautomator2)
            try:
                logger.info(f"🔍 Detecting UI automation capabilities for {serial}...")
                from app.infrastructure.drivers.adb import adb_driver

                # Run in executor to not block async loop
                loop = asyncio.get_running_loop()
                capabilities = await loop.run_in_executor(
                    None, adb_driver.detect_device_capabilities, serial
                )
                logger.info(f"✅ Device {serial} capabilities: {capabilities}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to detect capabilities for {serial}: {e}")

            await mirror_manager.on_device_connected(serial)
            from app.core.environment.event.publishers import publish_device_connected

            await publish_device_connected(device_id=serial, device_type="android")
            logger.info(f"🌅 Published device connected event: {serial}")
        else:
            logger.info(f"Device disconnected/offline: {serial} ({status})")
            mirror_manager.on_device_disconnected(serial)
            from app.core.environment.event.publishers import (
                publish_device_disconnected,
            )

            await publish_device_disconnected(device_id=serial)


# Global Watcher Instance
device_watcher = DeviceWatcher()
