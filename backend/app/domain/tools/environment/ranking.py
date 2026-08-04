"""
Ranking Tool - App usage priority sensing for macOS and Android.
"""

import asyncio
import logging
from typing import Literal

from app.core.environment.formatting import format_app_rankings
from app.core.environment.usage.ranker import UsageRanker
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(summary_template="evoloop.tool_summary.get_app_usage_ranker")
async def get_app_usage_ranker(platform: Literal["macos", "android"] = "macos", top_n: int = 10) -> str:
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

        try:
            return format_app_rankings(records, platform)
        except Exception as e:
            logger.error(f"Failed to render ranking list: {e}")
            return f"Found {len(records)} apps."

    except Exception as e:
        logger.error(f"[RankingTool] Failed to rank apps: {e}")
        return f"Error: Unable to rank apps. Details: {str(e)}"
