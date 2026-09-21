import logging
import time

from app.core.environment.constants import (
    DYNAMIC_APP_TRIAGE_BATCH_SIZE,
    dynamic_apps_key,
    processed_apps_key,
)
from app.core.environment.explorers.base import BaseExplorer
from app.infrastructure.cache import cache

logger = logging.getLogger(__name__)

# Track last log time to avoid repetitive "No new apps" logs
_last_no_apps_log: dict[str, float] = {}
_no_apps_log_interval: float = 300.0


class DynamicAppTriage(BaseExplorer):
    """
    Autonomous discovery of dynamic (coordinate-unstable) applications.
    LLM categorization runs in huey worker tasks, which persist verdicts to
    cache themselves (fire-and-forget from this scan loop).
    Platform-specific to avoid conflicts between different OS versions.
    """

    async def scan(self, *args, **kwargs) -> list:
        return []

    async def sync_dynamic_apps(
        self,
        macos_apps: list[str] = None,
        android_packages: list[str] = None,
        device_id: str | None = None,
    ):
        """
        Sync discovery state with cache and LLM.
        Supports partial updates (e.g. just macOS or just one Android device).
        Platform-specific storage prevents conflicts.
        """
        # Process by platform
        platforms_to_process = []
        if macos_apps:
            platforms_to_process.append(("macos", macos_apps))
        if android_packages:
            platforms_to_process.append(("android", android_packages))

        from app.core.environment.explorers.tasks import triage_app_batch

        for platform, apps in platforms_to_process:
            processed_key = processed_apps_key(platform)
            processed_apps = await cache.smembers(processed_key)

            new_apps = [a for a in apps if a not in processed_apps]

            if not new_apps:
                now = time.time()
                last_log = _last_no_apps_log.get(platform, 0)
                if now - last_log > _no_apps_log_interval:
                    logger.debug(
                        f"[DynamicAppTriage] No new {platform} apps to triage."
                    )
                    _last_no_apps_log[platform] = now
                continue

            logger.info(
                f"[DynamicAppTriage] Enqueuing {len(new_apps)} new {platform} apps "
                f"({DYNAMIC_APP_TRIAGE_BATCH_SIZE}/batch, fire-and-forget; verdicts are "
                "persisted by the worker task itself)"
            )
            for i in range(0, len(new_apps), DYNAMIC_APP_TRIAGE_BATCH_SIZE):
                batch = new_apps[i : i + DYNAMIC_APP_TRIAGE_BATCH_SIZE]
                try:
                    triage_app_batch.delay(batch, platform)
                except Exception as e:
                    logger.exception(f"[DynamicAppTriage] Failed to enqueue batch: {e}")

    @staticmethod
    async def get_dynamic_apps(platform: str = "android") -> set[str]:
        """Helper to fetch the current dynamic app set from cache for a specific platform.

        Pure dynamic configuration - no hardcoded fallbacks.
        Apps are classified via LLM triage and stored in cache.

        Args:
            platform: Platform identifier ("android", "macos", etc.)
        """
        try:
            dynamic_key = dynamic_apps_key(platform)
            app_ids = await cache.smembers(dynamic_key)
            return set(app_ids) if app_ids else set()
        except Exception as e:
            logger.exception(
                f"[DynamicAppTriage] Cache fetch failed for {platform}: {e}"
            )
            return set()
