import logging
import time
from typing import Any

from app.core.evocloud import evocloud_manager

logger = logging.getLogger(__name__)


class BenefitService:
    """
    Unified service for managing member benefits and entitlements.
    Acts as the source of truth for feature access gatekeeping in Python.
    """

    def __init__(self):
        # Local TTL Cache for benefits to reduce cloud latency
        # Cache structure: {member_id: (benefit_data, timestamp)}
        self._cache: dict[int, tuple[dict[str, Any], float]] = {}
        # Benefit definitions (Labels/Desc)
        self._definitions: dict[str, dict[str, str]] = {}
        self.CACHE_TTL = 60  # 60 seconds

    def invalidate_cache(self, member_id: int = None):
        """
        Clear local cache for a member or all members.
        """
        if member_id:
            if member_id in self._cache:
                del self._cache[member_id]
        else:
            self._cache.clear()
        self._definitions.clear()

    async def get_member_entitlements(self, member_id: int, token: str = None, force_refresh: bool = False) -> dict[str, Any]:
        """
        Fetch full entitlement set for a member from Member Center.
        """
        # 0. Force refresh: invalidate cache first
        if force_refresh:
            self.invalidate_cache(member_id)

        # 1. Check local cache
        if member_id in self._cache:
            data, ts = self._cache[member_id]
            if time.time() - ts < self.CACHE_TTL:
                return data

        # 2. Fetch from Cloud
        try:
            res = await evocloud_manager.api.get_member_benefits()
            if res.get("code") == 0:
                data = res.get("data", {})
                self._cache[member_id] = (data, time.time())
                
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
