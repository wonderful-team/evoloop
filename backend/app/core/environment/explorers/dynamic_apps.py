import json
import logging
from typing import Any

from app.core.environment.explorers.base import BaseExplorer
from app.infrastructure.database.redis import get_redis_client

logger = logging.getLogger(__name__)

REDIS_KEY_DYNAMIC_APPS = "system:dynamic_apps"
REDIS_KEY_APP_REASONING = "system:app_categorization"


class DynamicAppTriage(BaseExplorer):
    """
    Autonomous discovery of dynamic (coordinate-unstable) applications.
    Uses LLM to categorize apps and persists results in Redis.
    """

    async def scan(self, *args, **kwargs) -> list:
        # Not used directly for scan, but part of BaseExplorer interface
        return []

    async def sync_dynamic_apps(self, macos_apps: list[str] = None, android_packages: list[str] = None):
        """
        Sync discovery state with Redis and LLM.
        Supports partial updates (e.g. just macOS or just one Android device).
        """
        redis = await get_redis_client()
        
        # 1. Get all previously processed apps from Redis
        processed_key = "system:processed_apps"
        processed_apps = await redis.smembers(processed_key)
        
        all_new_apps = []
        if macos_apps:
            all_new_apps.extend([a for a in macos_apps if a not in processed_apps])
        if android_packages:
            all_new_apps.extend([p for p in android_packages if p not in processed_apps])

        if not all_new_apps:
            logger.debug("[DynamicAppTriage] No new apps to triage.")
            return

        logger.info(f"[DynamicAppTriage] Triaging {len(all_new_apps)} new apps via LLM...")
        
        # 2. LLM Triage
        triage_results = await self._triage_with_llm(all_new_apps)
        
        # 3. Update Redis
        if triage_results:
            pipe = redis.pipeline()
            for app_id, data in triage_results.items():
                is_dynamic = data.get("is_dynamic", False)
                reason = data.get("reason", "Unknown")
                
                # Mark as processed
                pipe.sadd(processed_key, app_id)
                
                if is_dynamic:
                    pipe.sadd(REDIS_KEY_DYNAMIC_APPS, app_id)
                    pipe.hset(REDIS_KEY_APP_REASONING, app_id, reason)
                    logger.info(f"[DynamicAppTriage] Marked '{app_id}' as DYNAMIC: {reason}")
                else:
                    logger.debug(f"[DynamicAppTriage] Marked '{app_id}' as STATIC")
            
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
    async def get_dynamic_apps() -> set[str]:
        """Helper to fetch the current dynamic app set from Redis + Hardcoded safeguards."""
        # 1. Hardcoded safeguards for common dynamic apps to ensure immediate safety
        # bundle_ids for common communication/scrolling apps
        known_dynamic = {
            "com.tencent.xinWeChat",  # WeChat
            "com.webex.meeting",      # Webex
            "com.microsoft.Teams",    # Teams
            "com.tinyspeck.slackmacgap", # Slack
            "work.feishu.main",       # Feishu
            "com.whatsapp.WhatsApp",  # WhatsApp
            "com.apple.Safari",       # Safari
            "com.google.Chrome",      # Chrome
        }
        
        try:
            redis = await get_redis_client()
            app_ids = await redis.smembers(REDIS_KEY_DYNAMIC_APPS)
            if app_ids:
                known_dynamic.update(app_ids)
        except Exception as e:
            logger.debug(f"[DynamicAppTriage] Redis fetch failed, using only hardcoded: {e}")
            
        return known_dynamic
