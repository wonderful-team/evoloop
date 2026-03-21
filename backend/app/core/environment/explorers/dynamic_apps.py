import json
import logging
from typing import Any

from app.core.environment.explorers.base import BaseExplorer
from app.infrastructure.cache import cache

logger = logging.getLogger(__name__)

REDIS_KEY_DYNAMIC_APPS_PREFIX = "system:dynamic_apps"
REDIS_KEY_APP_REASONING_PREFIX = "system:app_categorization"


class DynamicAppTriage(BaseExplorer):
    """
    Autonomous discovery of dynamic (coordinate-unstable) applications.
    Uses LLM to categorize apps and persists results in cache.
    Platform-specific to avoid conflicts between different OS versions.
    """

    @staticmethod
    def _get_dynamic_apps_key(platform: str) -> str:
        """Generate platform-specific cache key for dynamic apps."""
        return f"{REDIS_KEY_DYNAMIC_APPS_PREFIX}:{platform}"

    @staticmethod
    def _get_reasoning_key(platform: str) -> str:
        """Generate platform-specific cache key for app reasoning."""
        return f"{REDIS_KEY_APP_REASONING_PREFIX}:{platform}"

    async def scan(self, *args, **kwargs) -> list:
        # Not used directly for scan, but part of BaseExplorer interface
        return []

    async def sync_dynamic_apps(
        self,
        macos_apps: list[str] = None,
        android_packages: list[str] = None,
        device_id: str | None = None
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

        for platform, apps in platforms_to_process:
            # 1. Get all previously processed apps from cache for this platform
            processed_key = f"system:processed_apps:{platform}"
            processed_apps = await cache.smembers(processed_key)

            new_apps = [a for a in apps if a not in processed_apps]

            if not new_apps:
                logger.debug(f"[DynamicAppTriage] No new {platform} apps to triage.")
                continue

            logger.info(f"[DynamicAppTriage] Triaging {len(new_apps)} new {platform} apps via LLM...")

            # 2. LLM Triage
            triage_results = await self._triage_with_llm(new_apps)

            # 3. Update cache with platform-specific keys
            if triage_results:
                dynamic_key = self._get_dynamic_apps_key(platform)
                reasoning_key = self._get_reasoning_key(platform)

                pipe = cache.pipeline()
                for app_id, data in triage_results.items():
                    is_dynamic = data.get("is_dynamic", False)
                    reason = data.get("reason", "Unknown")

                    # Mark as processed (platform-specific)
                    pipe.sadd(processed_key, app_id)

                    if is_dynamic:
                        pipe.sadd(dynamic_key, app_id)
                        pipe.hset(reasoning_key, app_id, reason)
                        logger.info(f"[DynamicAppTriage] Marked '{platform}:{app_id}' as DYNAMIC: {reason}")
                    else:
                        logger.debug(f"[DynamicAppTriage] Marked '{platform}:{app_id}' as STATIC")

                await pipe.execute()

    async def _triage_with_llm(self, app_ids: list[str]) -> dict[str, dict]:
        """
        Use LLM to determine if apps have dynamic UI elements (scrolling lists, info streams, etc).
        """
        if not app_ids:
            return {}

        from langchain_core.messages import HumanMessage, SystemMessage
        from app.infrastructure.llm.factory import get_default_llm

        try:
            llm = get_default_llm()
            # Set temperature to 0 for deterministic triage
            llm.temperature = 0
            
            prompt = (
                "You are an expert in User Interface Analysis and Accessibility.\n"
                "I will give you a list of application Bundle IDs (macOS) or Package Names (Android).\n"
                "Determine if these apps have 'Coordinate-Unstable' interaction targets where buttons or list items frequently shift screen positions (typically due to scrolling).\n\n"
                "CRITICAL DISTINCTION:\n"
                "- is_dynamic: true -> Apps with scrolling message feeds, contact lists, or infinite-scrolling content. Interaction targets (like a specific chat or post) move when new items arrive or user scrolls. Examples: WeChat, WhatsApp, Telegram, Slack, Feishu, TikTok, News apps, Browsers.\n"
                "- is_dynamic: false -> Apps with auto-refreshing data but STABLE layout. If the buttons, sidebars, and control items stay in fixed positions even when data updates, it is STATIC. Examples: Terminal, Activity Monitor, Docker (Dashboards), VPN clients, calculators.\n\n"
                "For each app, provide a boolean 'is_dynamic' and a short 'reason'.\n"
                "Respond ONLY with a JSON object in this format:\n"
                "{\"results\": {\"com.example.app\": {\"is_dynamic\": true, \"reason\": \"...\"}}}\n\n"
                f"Apps to analyze:\n{chr(10).join(app_ids)}"
            )

            response = await llm.ainvoke([
                SystemMessage(content="You are a UI Dynamics Expert."),
                HumanMessage(content=prompt)
            ])

            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            
            data = json.loads(content)
            return data.get("results", {})
        except Exception as e:
            logger.error(f"[DynamicAppTriage] LLM Identification failed: {e}")
            return {}

    @staticmethod
    async def get_dynamic_apps(platform: str = "android") -> set[str]:
        """Helper to fetch the current dynamic app set from cache for a specific platform.

        Pure dynamic configuration - no hardcoded fallbacks.
        Apps are classified via LLM triage and stored in cache.

        Args:
            platform: Platform identifier ("android", "macos", etc.)
        """
        try:
            dynamic_key = f"{REDIS_KEY_DYNAMIC_APPS_PREFIX}:{platform}"
            app_ids = await cache.smembers(dynamic_key)
            return set(app_ids) if app_ids else set()
        except Exception as e:
            logger.error(f"[DynamicAppTriage] Cache fetch failed for {platform}: {e}")
            return set()
