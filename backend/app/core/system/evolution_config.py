from app.core.config import settings
from app.core.system.service import SystemConfigService


class EvolutionConfigService:
    KEY = "ENABLE_SELF_EVOLUTION"

    @staticmethod
    def is_enabled() -> bool:
        """
        Check if Self-Evolution is enabled.
        Logic: ENV variable acts as a master switch (must be True).
               Then checks DB configuration (defaults to True if ENV is True, for convenience? Or default False?)
               Let's say default False in DB to be safe.
        """
        # 1. Master Switch (ENV)
        if not settings.ENABLE_SELF_EVOLUTION:
            return False

        # 2. Runtime Switch (DB)
        # If DB key is missing, we default to False for safety.
        db_value = SystemConfigService.get_value(EvolutionConfigService.KEY, default="false")
        return str(db_value).lower() == "true"

    @staticmethod
    def set_enabled(enabled: bool) -> None:
        """
        Update the runtime switch.
        """
        SystemConfigService.set_value(
            EvolutionConfigService.KEY,
            "true" if enabled else "false",
            description="Runtime switch for Self-Evolution Loop",
        )
