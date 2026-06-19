import logging

from app.core.config import settings
from app.infrastructure.config import SystemConfigService
from app.infrastructure.database.resource_manager import db_resource_manager

logger = logging.getLogger(__name__)


def init() -> None:
    """
    Seed System Configuration from Environment/Settings.
    This ensures that on first run, the database is populated with valid defaults.
    """
    from sqlmodel import Session
    # Use sync engine from unified resource manager
    with Session(db_resource_manager.sync_engine) as session:
        # Seeding logic below uses SystemConfigiteService which internally uses session_scope/engine
        pass

    # 1. EVOCLOUD_DEVICE_NAME
    if not SystemConfigService.get_value("EVOCLOUD_DEVICE_NAME"):
        default_name = settings.EVOCLOUD_DEVICE_NAME
        if default_name:
            logger.info(f"Seeding EVOCLOUD_DEVICE_NAME from settings: {default_name}")
            SystemConfigService.set_value("EVOCLOUD_DEVICE_NAME", default_name, "Device identifier for EvoLoop Link")

    # 2. Embedding Configuration
    if not SystemConfigService.get_value("EMBEDDING_PROVIDER"):
        logger.info("EMBEDDING_PROVIDER not configured. Skipping automatic seeding — user must configure embedding explicitly.")

    # 3. Intent Classifier Configuration
    if not SystemConfigService.get_value("INTENT_MIN_CONFIDENCE"):
        logger.info("Seeding INTENT_MIN_CONFIDENCE...")
        SystemConfigService.set_value("INTENT_MIN_CONFIDENCE", "0.35", "Intent Classifier Threshold (0.0-1.0)")

    # 4. Agent Identity Configuration
    if not SystemConfigService.get_value("AGENT_NAME"):
        logger.info("Seeding AGENT_NAME...")
        SystemConfigService.set_value("AGENT_NAME", "EvoLoop", "Agent display name for LLM prompts")
    if not SystemConfigService.get_value("AGENT_COMPANY"):
        logger.info("Seeding AGENT_COMPANY...")
        SystemConfigService.set_value("AGENT_COMPANY", "上海方天画戟信息技术有限公司", "Agent developer company name")
    if not SystemConfigService.get_value("AGENT_WEBSITE"):
        logger.info("Seeding AGENT_WEBSITE...")
        SystemConfigService.set_value("AGENT_WEBSITE", "https://evoloop.cn", "Agent official website URL")

    # 5. LLM & Vision Configuration
    _seed_llm_config(SystemConfigService)


def _seed_llm_config(SystemConfigService):
    """Seed LLM and Vision configuration from settings if not already set."""
    if not SystemConfigService.get_value("LLM_PROVIDER"):
        logger.info("LLM_PROVIDER not configured. Skipping automatic seeding — user must configure LLM explicitly.")

    # Vision Model is no longer auto-seeded from a hardcoded default.
    if not SystemConfigService.get_value("VISION_MODEL"):
        logger.info("VISION_MODEL not configured. Skipping automatic seeding.")


def main() -> None:
    logger.info("Creating initial database data...")
    init()
    logger.info("Initial data creation complete.")


if __name__ == "__main__":
    main()
