"""
Environment Watcher - Background service for real-time environment updates.

This module provides a background watcher that periodically refreshes the
awakened state to detect device connections/disconnections and network changes.
"""

import asyncio
import logging

from app.core.environment.discovery import EnvironmentProbe

logger = logging.getLogger(__name__)


class EnvironmentWatcher:
    """
    Background service that monitors environment changes.
    
    Detects:
    - Android device connections/disconnections
    - Network connectivity changes
    - (Future) USB device changes
    """
    
    def __init__(self, refresh_interval: int = 30):
        """
        Initialize the environment watcher.
        
        Args:
            refresh_interval: Seconds between environment checks (default: 30)
        """
        self.refresh_interval = refresh_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._on_change_callbacks: list = []
    
    def on_change(self, callback):
        """Register a callback to be called when environment changes."""
        self._on_change_callbacks.append(callback)
    
    async def start(self):
        """Start the background watcher."""
        if self._running:
            logger.warning("EnvironmentWatcher already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info(f"🔭 EnvironmentWatcher started (interval: {self.refresh_interval}s)")
    
    async def stop(self):
        """Stop the background watcher."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🔭 EnvironmentWatcher stopped")
    
    async def _watch_loop(self):
        """Main watch loop that periodically checks for changes."""
        from app.core.environment import get_awakened_state, _refresh_state
        
        previous_device_ids = set()
        previous_network_status = None
        
        # Get initial state
        state = get_awakened_state()
        if state:
            previous_device_ids = {d.device_id for d in state.android_devices}
            previous_network_status = state.network.internet_connected if state.network else None
        
        while self._running:
            try:
                await asyncio.sleep(self.refresh_interval)
                
                if not self._running:
                    break
                
                # Skip polling Android if we have a real-time watcher active
                # DeviceWatcher already calls _refresh_state() on connection/disconnection
                # We only need to check macOS or Network here if we want periodic checks
                
                # For now, let's keep it but reduce frequency or scope if needed.
                # Actually, let's just make it focus on Network/Host if those are cheap.
                current_devices = [] 
                try:
                    # We still want to allow polling as a fallback, but maybe less aggressively
                    # Or check get_awakened_state and only probe if last update was long ago
                    current_devices = await EnvironmentProbe.probe_android_devices()
                except:
                    pass

                current_network = await EnvironmentProbe.probe_network()
                
                current_device_ids = {d.device_id for d in current_devices}
                current_network_status = current_network.internet_connected
                
                changes_detected = False
                
                # Check for device changes
                added_devices = current_device_ids - previous_device_ids
                removed_devices = previous_device_ids - current_device_ids
                
                if added_devices:
                    logger.info(f"📱 New devices connected: {added_devices}")
                    changes_detected = True
                
                if removed_devices:
                    logger.info(f"📱 Devices disconnected: {removed_devices}")
                    changes_detected = True
                
                # Check for network changes
                if current_network_status != previous_network_status:
                    status_str = "Online" if current_network_status else "Offline"
                    logger.info(f"🌐 Network status changed: {status_str}")
                    changes_detected = True
                
                # If changes detected, refresh the full state
                if changes_detected:
                    await _refresh_state()
                    
                    # Notify callbacks
                    for callback in self._on_change_callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback()
                            else:
                                callback()
                        except Exception as e:
                            logger.warning(f"Callback error: {e}")
                
                # Update previous state
                previous_device_ids = current_device_ids
                previous_network_status = current_network_status
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"EnvironmentWatcher error: {e}")
                await asyncio.sleep(5)  # Brief pause before retry


# Global watcher instance
environment_watcher = EnvironmentWatcher()
