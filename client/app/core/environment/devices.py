"""
Local Device Pool Manager for Android hardware resources.

Replaces Redis-backed distributed locking with local asyncio locks
for Client-only single-process architecture.
"""

import asyncio
import logging
import time
from typing import Optional, List

from app.core.environment import get_awakened_state

logger = logging.getLogger(__name__)

# Local in-memory device locks
_device_locks: dict[str, asyncio.Lock] = {}
_device_owners: dict[str, str] = {}


class DevicePool:
    """
    Local manager for Android hardware resources.
    Integrates with AwakenedState to track physical connectivity and
    uses local locks for task assignment (Client-only).
    """

    @classmethod
    async def get_available_devices(cls) -> List[str]:
        """
        Get all devices that are currently 'device' status in AwakenedState.
        """
        state = get_awakened_state()
        if not state or not state.android_devices:
            return []

        return [d.device_id for d in state.android_devices if d.is_reachable]

    @classmethod
    async def reserve_device(cls, task_id: str, preferred_device: Optional[str] = None, timeout: int = 30) -> Optional[str]:
        """
        Try to reserve a device for a specific task.
        Uses local locks for exclusive access.

        Args:
            task_id: The ID of the task requesting the device.
            preferred_device: Optional specific device_id to target.
            timeout: How long to wait for a device if none are free.

        Returns:
            The device_id if successfully reserved, else None.
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            available_serials = await cls.get_available_devices()
            if not available_serials:
                await asyncio.sleep(2)
                continue

            # If a preferred device is specified, try it first
            targets = [preferred_device] if preferred_device and preferred_device in available_serials else available_serials

            for serial in targets:
                # Initialize lock if needed
                if serial not in _device_locks:
                    _device_locks[serial] = asyncio.Lock()

                # Try to acquire lock non-blocking
                if not _device_locks[serial].locked():
                    await _device_locks[serial].acquire()
                    _device_owners[serial] = task_id
                    logger.info(f"Locked device {serial} for task {task_id}")
                    return serial

            await asyncio.sleep(1)  # Poll interval

        return None

    @classmethod
    async def release_device(cls, device_id: str, task_id: str):
        """
        Release a previously reserved device.
        Only releases if the task_id still matches.
        """
        lock = _device_locks.get(device_id)
        owner = _device_owners.get(device_id)

        if owner == task_id:
            if lock and lock.locked():
                lock.release()
            _device_owners.pop(device_id, None)
            logger.info(f"Released device {device_id} from task {task_id}")
        else:
            logger.warning(f"Task {task_id} tried to release device {device_id} but owner is {owner}")

    @classmethod
    async def list_status(cls) -> List[dict]:
        """
        Provide a detailed status map of all physical devices and their current owners.
        """
        serials = await cls.get_available_devices()

        results = []
        for s in serials:
            lock = _device_locks.get(s)
            is_locked = lock.locked() if lock else False
            owner = _device_owners.get(s)
            results.append({
                "device_id": s,
                "status": "busy" if is_locked else "idle",
                "owner": owner
            })
        return results
