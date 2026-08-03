"""Benefit service — manages member benefits and entitlements."""

import asyncio
import json
import logging
from typing import Any

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.infrastructure.cache import cache

logger = logging.getLogger(__name__)


@event_register()
class BenefitAuthHandler:
    """Refresh or clear benefit cache on auth state changes."""

    @event_subscribe(SystemEventType.USER_LOGGED_IN)
    async def on_user_logged_in(self, event):
        """Clear stale cache so next request fetches fresh entitlements."""
        logger.info("[BenefitService] User logged in, invalidating benefit cache...")
        member_id = event.member_id
        await benefit_service.invalidate_cache(member_id)

    @event_subscribe(SystemEventType.USER_LOGGED_OUT)
    async def on_user_logged_out(self, event):
        """Clear all cached benefits on logout."""
        logger.info("[BenefitService] User logged out, clearing benefit cache...")
        member_id = event.member_id
        await benefit_service.invalidate_cache(member_id)


class BenefitService:
    """
    Unified service for managing member benefits and entitlements.
    Acts as the source of truth for feature access gatekeeping in Python.
    """

    def __init__(self):
        self._definitions: dict[str, dict[str, str]] = {}
        self.CACHE_TTL = 120
        self._pending_fetches: dict[int, asyncio.Task] = {}

    async def invalidate_cache(self, member_id: int = None):
        if member_id:
            await cache.delete(f"evoloop:benefits:{member_id}")

    async def get_member_entitlements(self, member_id: int, token: str = None, force_refresh: bool = False) -> dict[str, Any]:
        if member_id in self._pending_fetches and not force_refresh:
            return await self._pending_fetches[member_id]

        cache_key = f"evoloop:benefits:{member_id}"

        if force_refresh:
            await self.invalidate_cache(member_id)

        cached_data_str = await cache.get(cache_key)
        if cached_data_str:
            try:
                data = json.loads(cached_data_str)
                defs = data.get("definitions", {})
                if defs:
                    self._definitions.update(defs)
                return data
            except json.JSONDecodeError:
                pass

        async def _fetch():
            try:
                from app.core.evocloud import evocloud_manager

                res = await evocloud_manager.api.get_member_benefits(token=token)
                if res.get("code") == 0:
                    data = res.get("data", {})
                    await cache.set(cache_key, json.dumps(data), ex=self.CACHE_TTL)

                    defs = data.get("definitions", {})
                    if defs:
                        self._definitions.update(defs)

                    return data

                logger.warning(f"Failed to fetch benefits for {member_id}: {res.get('message')}")
                return {}
            except Exception as e:
                logger.error(f"Benefit Service error for {member_id}: {e}")
                return {}

        task = asyncio.create_task(_fetch())
        self._pending_fetches[member_id] = task
        try:
            return await task
        finally:
            self._pending_fetches.pop(member_id, None)

    def get_benefit_label(self, feature_code: str) -> str:
        return self._definitions.get(feature_code, {}).get("name", feature_code)

    def get_benefit_description(self, feature_code: str) -> str:
        return self._definitions.get(feature_code, {}).get("desc", "")

    async def has_benefit(self, member_id: int, feature_code: str, token: str = None) -> bool:
        data = await self.get_member_entitlements(member_id, token)

        if data.get("is_expired", False):
            return False

        benefits = data.get("benefits", {})

        if feature_code in benefits:
            val = benefits[feature_code]
            if isinstance(val, bool):
                return val
            if isinstance(val, int | float):
                return val > 0
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes", "on")

        feature_list = data.get("feature_list", [])
        if feature_code in feature_list:
            return True

        return False

    async def check_multiple_benefits(self, benefit_codes: list[str], member_id: int) -> dict[str, bool]:
        try:
            data = await self.get_member_entitlements(member_id)

            if data.get("is_expired", False):
                return dict.fromkeys(benefit_codes, False)

            benefits = data.get("benefits", {})

            result = {}
            for code in benefit_codes:
                val = benefits.get(code, False)
                result[code] = val if isinstance(val, bool) else (val > 0 if isinstance(val, int | float) else False)
            return result
        except Exception as e:
            logger.error(f"Batch benefit check failed: {e}")
            return dict.fromkeys(benefit_codes, False)


benefit_service = BenefitService()
