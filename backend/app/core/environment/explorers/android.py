import logging

from app.core.environment.explorers.base import BaseExplorer
from app.infrastructure.drivers.adb import adb_driver

logger = logging.getLogger(__name__)


class AndroidExplorer(BaseExplorer):
    """
    Android-specific discovery logic.
    """

    async def scan(self, device_id: str) -> list[str]:
        """Simple scan for installed packages with dynamic triage."""
        try:
            packages = adb_driver.list_installed_apps(device_id=device_id)

            # Autonomous triage for discovered packages
            from app.core.environment.explorers.dynamic_apps import DynamicAppTriage

            triage = DynamicAppTriage()
            await triage.sync_dynamic_apps(android_packages=packages)

            return packages
        except Exception as e:
            logger.error(f"Android scan failed for {device_id}: {e}")
            return []
