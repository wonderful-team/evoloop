import asyncio
import logging
import time

from app.core.environment import get_awakened_state
from app.infrastructure.cache import cache

logger = logging.getLogger(__name__)

REDIS_KEY_DEVICE_LOCK_PREFIX = "device:lock:"
REDIS_KEY_DEVICE_QUEUE = "device:available_pool"


class DevicePool:
    """
    Cache-backed manager for Android hardware resources.
    Integrates with AwakenedState to track physical connectivity and
    uses cache locks to handle distributed task assignment.
    """

    @classmethod
    async def get_available_devices(cls) -> list[str]:
        """
        Get all devices that are currently 'device' status in AwakenedState.
        """
        state = get_awakened_state()
        if not state or not state.android_devices:
            return []

        return [d.device_id for d in state.android_devices if d.is_reachable]

    @classmethod
    async def reserve_device(cls, task_id: str, preferred_device: str | None = None, timeout: int = 30) -> str | None:
        """
        Try to reserve a device for a specific task.
        Uses cache to ensure exclusive access.
        
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
                lock_key = f"{REDIS_KEY_DEVICE_LOCK_PREFIX}{serial}"
                # Atomic reservation: write our task_id, then verify we own it.
                # This closes the get-then-set race: if two tasks both see
                # current is None, only the one whose write is observed by
                # the subsequent get wins.
                current = await cache.get(lock_key)
                if current is None:
                    await cache.set(lock_key, task_id, ex=3600)
                    # Re-read to confirm ownership (handles concurrent writers)
                    owner = await cache.get(lock_key)
                    if owner == task_id:
                        logger.info(f"Locked device {serial} for task {task_id}")
                        return serial
                    else:
                        logger.debug(f"[DevicePool] Lost race for {serial}, owner={owner}")

            await asyncio.sleep(1) # Poll interval

        return None

    @classmethod
    async def release_device(cls, device_id: str, task_id: str):
        """
        Release a previously reserved device.
        Only releases if the task_id still matches.
        """
        lock_key = f"{REDIS_KEY_DEVICE_LOCK_PREFIX}{device_id}"

        current_owner = await cache.get(lock_key)
        if current_owner == task_id:
            await cache.delete(lock_key)
            logger.info(f"Released device {device_id} from task {task_id}")
        else:
            logger.warning(f"Task {task_id} tried to release device {device_id} but owner is {current_owner}")

    @classmethod
    async def list_status(cls) -> list[dict]:
        """
        Provide a detailed status map of all physical devices and their current owners.
        """
        serials = await cls.get_available_devices()

        results = []
        for s in serials:
            owner = await cache.get(f"{REDIS_KEY_DEVICE_LOCK_PREFIX}{s}")
            results.append({
                "device_id": s,
                "status": "busy" if owner else "idle",
                "owner": owner
            })
        return results
