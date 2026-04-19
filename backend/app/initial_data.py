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

    # 1. WORKSPACE_ROOT
    if not SystemConfigService.get_value("WORKSPACE_ROOT"):
        default_root = settings.WORKSPACE_ROOT
        if default_root:
            logger.info(f"Seeding WORKSPACE_ROOT from settings: {default_root}")
            SystemConfigService.set_value("WORKSPACE_ROOT", default_root, "Root directory for workspace/project storage")
        else:
            logger.info("WORKSPACE_ROOT not configured. User will be prompted to set it during initialization.")

    # 2. EVOCLOUD_DEVICE_NAME
    if not SystemConfigService.get_value("EVOCLOUD_DEVICE_NAME"):
        default_name = settings.EVOCLOUD_DEVICE_NAME
        if default_name:
            logger.info(f"Seeding EVOCLOUD_DEVICE_NAME from settings: {default_name}")
            SystemConfigService.set_value("EVOCLOUD_DEVICE_NAME", default_name, "Device identifier for EvoLoop Link")

    # 3. PROJECT_DISCOVERY_ENABLED
    if not SystemConfigService.get_value("PROJECT_DISCOVERY_ENABLED"):
        default_discovery = "true" if settings.ENABLE_PROJECT_DISCOVERY else "false"
        logger.info(f"Seeding PROJECT_DISCOVERY_ENABLED from settings: {default_discovery}")
        SystemConfigService.set_value(
            "PROJECT_DISCOVERY_ENABLED", 
            default_discovery, 
            "Enable or disable automatic project discovery in workspace (true/false)"
        )

    # 4. Embedding Configuration
    if not SystemConfigService.get_value("EMBEDDING_PROVIDER"):
        logger.info("Seeding Embedding Configuration from settings...")
        SystemConfigService.set_value(
            "EMBEDDING_PROVIDER",
            settings.EMBEDDING_PROVIDER,
            "Embedding Provider (openai, ollama, dashscope, huggingface, local)"
        )
        SystemConfigService.set_value(
            "EMBEDDING_BASE_URL",
            settings.EMBEDDING_BASE_URL or settings.OPENAI_BASE_URL,
            "Embedding Base URL"
        )
        SystemConfigService.set_value(
            "EMBEDDING_MODEL",
            settings.EMBEDDING_MODEL_NAME,
            "Embedding Model Name"
        )
        SystemConfigService.set_value(
            "EMBEDDING_API_KEY",
            settings.OPENAI_API_KEY,
            "Embedding API Key"
        )
        SystemConfigService.set_value(
            "EMBEDDING_DIMENSIONS",
            str(settings.EMBEDDING_DIMENSIONS),
            "Embedding Dimensions"
        )

    # 5. Intent Classifier Configuration
    if not SystemConfigService.get_value("INTENT_MIN_CONFIDENCE"):
        logger.info("Seeding INTENT_MIN_CONFIDENCE...")
        SystemConfigService.set_value("INTENT_MIN_CONFIDENCE", "0.35", "Intent Classifier Threshold (0.0-1.0)")

    # 6. LLM & Vision Configuration
    _seed_llm_config(SystemConfigService)


def _seed_llm_config(SystemConfigService):
    """Seed LLM and Vision configuration from settings if not already set."""
    if not SystemConfigService.get_value("LLM_PROVIDER"):
        logger.info("Seeding LLM Configuration from settings...")

        provider = "openai"  # default
        if settings.ANTHROPIC_API_KEY:
            provider = "anthropic"
        elif settings.OPENAI_API_KEY and "localhost" in settings.OPENAI_BASE_URL:
            provider = "ollama"

        SystemConfigService.set_value("LLM_PROVIDER", provider, "LLM Provider (openai, anthropic, ollama)")
        SystemConfigService.set_value("LLM_BASE_URL", settings.OPENAI_BASE_URL, "LLM API Base URL")
        SystemConfigService.set_value("LLM_MODEL", settings.OPENAI_MODEL_NAME, "LLM Model Name")
        SystemConfigService.set_value("LLM_API_KEY", settings.OPENAI_API_KEY, "LLM API Key")
        
        # Config type: "platform" (use Gateway) or "custom" (use own key)
        SystemConfigService.set_value("LLM_CONFIG_TYPE", "custom", "LLM Config Type (platform, custom)")

    # Seed Vision Model (if not set)
    if not SystemConfigService.get_value("VISION_MODEL"):
        vision_model = getattr(settings, 'VISION_MODEL', settings.OPENAI_MODEL_NAME)
        logger.info(f"Seeding VISION_MODEL from settings: {vision_model}")
        SystemConfigService.set_value("VISION_MODEL", vision_model, "Vision Model Name (Multimodal)")


def main() -> None:
    logger.info("Creating initial database data...")
    init()
    logger.info("Initial data creation complete.")


if __name__ == "__main__":
    main()
