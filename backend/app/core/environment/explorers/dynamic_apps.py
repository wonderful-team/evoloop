import logging
import time

from app.constants import CACHE_KEY_DYNAMIC_APPS_PREFIX
from app.core.environment.constants import (
    CACHE_KEY_APP_REASONING_PREFIX,
    DYNAMIC_APP_TRIAGE_BATCH_SIZE,
)
from app.core.environment.explorers.base import BaseExplorer
from app.infrastructure.cache import cache

logger = logging.getLogger(__name__)

# Track last log time to avoid repetitive "No new apps" logs
_last_no_apps_log: dict[str, float] = {}
_no_apps_log_interval: float = 300.0

_TASK_TIMEOUT = 120.0


class DynamicAppTriage(BaseExplorer):
    """
    Autonomous discovery of dynamic (coordinate-unstable) applications.
    Uses LLM to categorize apps and persists results in cache.
    Platform-specific to avoid conflicts between different OS versions.
    """

    @staticmethod
    def _get_dynamic_apps_key(platform: str) -> str:
        return f"{CACHE_KEY_DYNAMIC_APPS_PREFIX}:{platform}"

    @staticmethod
    def _get_reasoning_key(platform: str) -> str:
        return f"{CACHE_KEY_APP_REASONING_PREFIX}:{platform}"

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
            processed_key = f"system:processed_apps:{platform}"
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
                f"[DynamicAppTriage] Triaging {len(new_apps)} new {platform} apps ({DYNAMIC_APP_TRIAGE_BATCH_SIZE} per batch)..."
            )

            all_results = {}
            for i in range(0, len(new_apps), DYNAMIC_APP_TRIAGE_BATCH_SIZE):
                batch = new_apps[i : i + DYNAMIC_APP_TRIAGE_BATCH_SIZE]
                try:
                    result = await triage_app_batch.delay(batch).get(
                        timeout=_TASK_TIMEOUT
                    )
                    if result:
                        all_results.update(result)
                except Exception as e:
                    logger.exception(f"[DynamicAppTriage] Batch task failed: {e}")

            if all_results:
                dynamic_key = self._get_dynamic_apps_key(platform)
                reasoning_key = self._get_reasoning_key(platform)

                pipe = cache.pipeline()
                for app_id, data in all_results.items():
                    is_dynamic = data.get("is_dynamic", False)
                    reason = data.get("reason", "Unknown")

                    pipe.sadd(processed_key, app_id)

                    if is_dynamic:
                        pipe.sadd(dynamic_key, app_id)
                        pipe.hset(reasoning_key, app_id, reason)
                        logger.info(
                            f"[DynamicAppTriage] Marked '{platform}:{app_id}' as DYNAMIC: {reason}"
                        )
                    else:
                        logger.debug(
                            f"[DynamicAppTriage] Marked '{platform}:{app_id}' as STATIC"
                        )

                await pipe.execute()

    @staticmethod
    async def get_dynamic_apps(platform: str = "android") -> set[str]:
        """Helper to fetch the current dynamic app set from cache for a specific platform.

        Pure dynamic configuration - no hardcoded fallbacks.
        Apps are classified via LLM triage and stored in cache.

        Args:
            platform: Platform identifier ("android", "macos", etc.)
        """
        try:
            dynamic_key = f"{CACHE_KEY_DYNAMIC_APPS_PREFIX}:{platform}"
            app_ids = await cache.smembers(dynamic_key)
            return set(app_ids) if app_ids else set()
        except Exception as e:
            logger.exception(
                f"[DynamicAppTriage] Cache fetch failed for {platform}: {e}"
            )
            return set()
