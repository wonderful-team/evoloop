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
            try:
                from app.core.environment.explorers.dynamic_apps import DynamicAppTriage
                triage = DynamicAppTriage()
                await triage.sync_dynamic_apps(android_packages=packages)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as triage_e:
                logger.warning(f"Dynamic app triage failed for {device_id}: {triage_e}")

            return packages
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"Android scan failed for {device_id}: {e}")
            return []
