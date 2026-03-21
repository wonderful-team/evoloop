"""
Ranking Tool - App usage priority sensing for macOS and Android.
"""
import asyncio
import logging
from typing import Literal

from app.core.environment.usage.ranker import UsageRanker
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    name_map={"zh": "获取应用使用排名", "en": "Get App Usage Ranker"}
)
async def get_app_usage_ranker(
    platform: Literal["macos", "android"] = "macos",
    top_n: int = 10
) -> str:
    """
    Ranks applications based on their usage patterns (recency, frequency, running status).
    
    This tool helps you identify which apps are most important to the user in the current environment.
    A high priority score (0.0 to 1.0) indicates the app is likely a primary work tool.
    
    Args:
        platform: The target platform ("macos" or "android").
        top_n: The number of top apps to return (default: 10).
        
    Returns:
        A formatted list of applications with their priority scores and usage stats.
    """
    try:
        # Note: UsageRanker.rank_macos_apps and rank_android_apps are sync but involve subprocess/adb
        if platform == "macos":
            from app.infrastructure.drivers.macos import macos_driver
            apps = macos_driver.list_installed_apps()
            records = await asyncio.to_thread(UsageRanker.rank_macos_apps, apps, top_n=top_n)
        else:
            from app.infrastructure.drivers.adb import adb_driver
            # For Android, we need a device_id. For now, use the first connected device if multiple.
            devices = adb_driver.list_devices()
            if not devices:
                return "Error: No Android devices found for ranking."
            device_id = devices[0]["serial"]
            packages = adb_driver.list_installed_apps(device_id=device_id)
            records = await asyncio.to_thread(UsageRanker.rank_android_apps, device_id, packages, top_n=top_n)

        if not records:
            return f"No usage data available for {platform}."

        lines = [f"Top {len(records)} {platform} applications by usage:"]
        for r in records:
            status = " [RUNNING]" if r.is_running else ""
            lines.append(f"- {r.app_name} ({r.bundle_id}): Score {r.priority_score:.2f}{status}")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"[RankingTool] Failed to rank apps: {e}")
        return f"Error: Unable to rank apps. Details: {str(e)}"
