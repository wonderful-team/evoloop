import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import engine
from app.core.environment.explorers.base import BaseExplorer
from app.models.atlas import AtlasDynamicApp, AtlasProcessedApp

logger = logging.getLogger(__name__)


class DynamicAppTriage(BaseExplorer):
    """
    Autonomous discovery of dynamic (coordinate-unstable) applications.
    Uses LLM to categorize apps and persists results in SQLite.
    Platform-specific to avoid conflicts between different OS versions.
    """

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
        Sync discovery state with SQLite and LLM.
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
            # 1. Get all previously processed apps from SQLite for this platform
            with Session(engine) as session:
                stmt = select(AtlasProcessedApp.bundle_id).where(
                    AtlasProcessedApp.platform == platform
                )
                processed_apps = set(session.execute(stmt).scalars().all())

            new_apps = [a for a in apps if a not in processed_apps]

            if not new_apps:
                logger.debug(f"[DynamicAppTriage] No new {platform} apps to triage.")
                continue

            logger.info(f"[DynamicAppTriage] Triaging {len(new_apps)} new {platform} apps via LLM...")

            # 2. LLM Triage
            triage_results = await self._triage_with_llm(new_apps)

            # 3. Update SQLite with platform-specific records
            if triage_results:
                with Session(engine) as session:
                    for app_id, data in triage_results.items():
                        is_dynamic = data.get("is_dynamic", False)
                        reason = data.get("reason", "Unknown")

                        # Mark as processed
                        processed = AtlasProcessedApp(
                            bundle_id=app_id,
                            platform=platform,
                            is_dynamic=is_dynamic,
                            reason=reason,
                        )
                        session.add(processed)

                        # If dynamic, also add to dynamic apps table
                        if is_dynamic:
                            # Check if already exists
                            stmt = select(AtlasDynamicApp).where(
                                AtlasDynamicApp.bundle_id == app_id,
                                AtlasDynamicApp.platform == platform,
                            )
                            existing = session.execute(stmt).scalar_one_or_none()
                            if not existing:
                                dynamic_app = AtlasDynamicApp(
                                    bundle_id=app_id,
                                    platform=platform,
                                    reason=reason,
                                )
                                session.add(dynamic_app)
                            logger.info(f"[DynamicAppTriage] Marked '{platform}:{app_id}' as DYNAMIC: {reason}")
                        else:
                            logger.debug(f"[DynamicAppTriage] Marked '{platform}:{app_id}' as STATIC")

                    session.commit()

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
                '{"results": {"com.example.app": {"is_dynamic": true, "reason": "..."}}}\n\n'
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
        """Helper to fetch the current dynamic app set from SQLite for a specific platform.

        Pure dynamic configuration - no hardcoded fallbacks.
        Apps are classified via LLM triage and stored in SQLite.

        Args:
            platform: Platform identifier ("android", "macos", etc.)
        """
        try:
            with Session(engine) as session:
                stmt = select(AtlasDynamicApp.bundle_id).where(
                    AtlasDynamicApp.platform == platform
                )
                app_ids = session.execute(stmt).scalars().all()
                return set(app_ids)
        except Exception as e:
            logger.error(f"[DynamicAppTriage] SQLite fetch failed for {platform}: {e}")
            return set()
