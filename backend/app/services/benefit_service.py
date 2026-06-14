import logging
import json
import time
from typing import Any

from app.core.evocloud import evocloud_manager
from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.infrastructure.cache import cache

logger = logging.getLogger(__name__)


# --- Event Subscribers ---

@event_register()
class BenefitAuthHandler:
    """Refresh or clear benefit cache on auth state changes."""

    @event_subscribe(SystemEventType.USER_LOGGED_IN)
    async def on_user_logged_in(self, event):
        """Clear stale cache so next request fetches fresh entitlements."""
        logger.info("[BenefitService] User logged in, invalidating benefit cache...")
        member_id = getattr(event, "member_id", None)
        await benefit_service.invalidate_cache(member_id)

    @event_subscribe(SystemEventType.USER_LOGGED_OUT)
    async def on_user_logged_out(self, event):
        """Clear all cached benefits on logout."""
        logger.info("[BenefitService] User logged out, clearing benefit cache...")
        member_id = getattr(event, "member_id", None)
        await benefit_service.invalidate_cache(member_id)


class BenefitService:
    """
    Unified service for managing member benefits and entitlements.
    Acts as the source of truth for feature access gatekeeping in Python.
    """

    def __init__(self):
        # Local cache is removed in favor of shared infrastructure cache
        # Benefit definitions (Labels/Desc)
        self._definitions: dict[str, dict[str, str]] = {}
        self.CACHE_TTL = 120  # Changed to 2 minutes
        self._pending_fetches = {}

    async def invalidate_cache(self, member_id: int = None):
        """
        Clear shared cache for a member.
        """
        if member_id:
            await cache.delete(f"evoloop:benefits:{member_id}")
        # Note: clearing all members is not easily supported in simple KV cache without scanning,
        # but the only caller without member_id is global logout/login events which we can ignore
        # or handle differently if needed.

    async def get_member_entitlements(self, member_id: int, token: str = None, force_refresh: bool = False) -> dict[str, Any]:
        """
        Fetch full entitlement set for a member from Member Center.
        """
        import asyncio
        
        # 0. Prevent cache stampede (singleflight)
        if member_id in self._pending_fetches and not force_refresh:
            return await self._pending_fetches[member_id]
            
        cache_key = f"evoloop:benefits:{member_id}"

        # 0. Force refresh: invalidate cache first
        if force_refresh:
            await self.invalidate_cache(member_id)

        # 1. Check shared cache
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

        # 2. Fetch from Cloud (wrapped in task for singleflight)
        async def _fetch():
            try:
                res = await evocloud_manager.api.get_member_benefits(token=token)
                if res.get("code") == 0:
                    data = res.get("data", {})
                    await cache.set(cache_key, json.dumps(data), ex=self.CACHE_TTL)
                    
                    # Update global definitions cache
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
        """
        Get the human-readable label for a benefit code.
        """
        return self._definitions.get(feature_code, {}).get("name", feature_code)

    def get_benefit_description(self, feature_code: str) -> str:
        """
        Get the description for a benefit code.
        """
        return self._definitions.get(feature_code, {}).get("desc", "")

    async def has_benefit(self, member_id: int, feature_code: str, token: str = None) -> bool:
        """
        Check if a member has a specific capability.
        """
        data = await self.get_member_entitlements(member_id, token)

        # Subscription expired: no benefits regardless of level config
        if data.get("is_expired", False):
            return False

        # Features are usually in result['benefits'] dictionary or ['feature_list'] array
        # Based on b2c_mall schema, they are in the subscription_features list
        benefits = data.get("benefits", {})

        # 1. Check dictionary of boolean/numeric values
        if feature_code in benefits:
            val = benefits[feature_code]
            if isinstance(val, bool):
                return val
            if isinstance(val, int | float):
                return val > 0
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes", "on")

        # 2. Check feature list array (if returned as list)
        feature_list = data.get("feature_list", [])
        if feature_code in feature_list:
            return True

        return False

    async def check_multiple_benefits(self, benefit_codes: list[str], member_id: int) -> dict[str, bool]:
        """
        Check multiple benefits in one go.
        Fetches all entitlements once and checks each code.
        """
        try:
            data = await self.get_member_entitlements(member_id)

            # Subscription expired: all benefits denied
            if data.get("is_expired", False):
                return {code: False for code in benefit_codes}

            benefits = data.get("benefits", {})

            result = {}
            for code in benefit_codes:
                val = benefits.get(code, False)
                result[code] = val if isinstance(val, bool) else (val > 0 if isinstance(val, int | float) else False)
            return result
        except Exception as e:
            logger.error(f"Batch benefit check failed: {e}")
            return {code: False for code in benefit_codes}


# Global instance
benefit_service = BenefitService()
