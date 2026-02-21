
import logging
import asyncio
import json
from typing import List

from app.core.environment.explorers.base import BaseExplorer
from app.infrastructure.drivers.adb import adb_driver

logger = logging.getLogger(__name__)


class AndroidExplorer(BaseExplorer):
    """
    Android-specific discovery logic.
    """

    async def scan(self, device_id: str) -> list[str]:
        """Simple scan for installed packages."""
        try:
            return adb_driver.list_installed_apps(device_id=device_id)
        except Exception as e:
            logger.error(f"Android scan failed for {device_id}: {e}")
            return []
