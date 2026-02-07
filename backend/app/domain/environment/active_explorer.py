import logging
import asyncio
from typing import Optional, List
from datetime import datetime

from app.domain.environment.models import AndroidDevice, MacOSEnvironment
from app.domain.environment.explorers.android import AndroidExplorer
from app.domain.environment.explorers.macos import MacOSExplorer

logger = logging.getLogger(__name__)


class ActiveExplorer:
    """
    Active Discovery System - Orchestrator.
    Delegates platform-specific scouting to specialized explorers.
    """

    @classmethod
    async def scout(cls, macos: Optional[MacOSEnvironment], android_devices: List[AndroidDevice]) -> dict:
        """
        Orchestrate the active discovery process across all platforms.
        """
        report = {
            "android": {},
            "macos": {},
            "timestamp": datetime.now().isoformat()
        }

        # 1. Android Scout
        if android_devices:
            explorer = AndroidExplorer()
            tasks = [explorer.scout(device.device_id) for device in android_devices]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for device, res in zip(android_devices, results):
                if isinstance(res, Exception):
                    logger.error(f"Failed to scout device {device.device_id}: {res}")
                    report["android"][device.device_id] = {"error": str(res)}
                else:
                    report["android"][device.device_id] = res

        # 2. MacOS Scout
        if macos:
            logger.info("🔍 [ActiveExplorer] Delegation -> MacOSExplorer")
            explorer = MacOSExplorer()
            try:
                report["macos"] = await explorer.scout(macos)
            except Exception as e:
                logger.error(f"Failed to scout MacOS: {e}")
                report["macos"] = {"error": str(e)}

        return report
