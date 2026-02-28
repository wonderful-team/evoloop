import asyncio
import logging
import os

from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine, init_db
from app.core.tools.mcp.client import mcp_client_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init() -> None:
    with Session(engine) as session:
        init_db(session)

    # Seed System Configuration from Environment/Settings
    # This ensures that on first run, the database is populated with valid defaults
    from app.infrastructure.config.service import SystemConfigService

    # 1. PROJECTS_ROOT
    if not SystemConfigService.get_value("PROJECTS_ROOT"):
        default_root = settings.PROJECTS_ROOT
        logger.info(f"Seeding PROJECTS_ROOT from settings: {default_root}")
        SystemConfigService.set_value("PROJECTS_ROOT", default_root, "Root directory for project storage")

    # 2. EVOCLOUD_DEVICE_NAME
    if not SystemConfigService.get_value("EVOCLOUD_DEVICE_NAME"):
        default_name = settings.EVOCLOUD_DEVICE_NAME
        if default_name:
            logger.info(f"Seeding EVOCLOUD_DEVICE_NAME from settings: {default_name}")
            SystemConfigService.set_value("EVOCLOUD_DEVICE_NAME", default_name, "Device identifier for EvoLoop Link")

    # 3. Embedding Configuration
    if not SystemConfigService.get_value("EMBEDDING_PROVIDER"):
        # Default to 'openai' or infer from settings?
        # We'll use values from settings as initial defaults
        logger.info("Seeding Embedding Configuration from settings...")
        SystemConfigService.set_value("EMBEDDING_PROVIDER", "openai", "Embedding Provider")
        SystemConfigService.set_value("EMBEDDING_BASE_URL", settings.OPENAI_BASE_URL, "Embedding Base URL")
        SystemConfigService.set_value("EMBEDDING_MODEL", settings.EMBEDDING_MODEL_NAME, "Embedding Model Name")
        SystemConfigService.set_value("EMBEDDING_API_KEY", settings.OPENAI_API_KEY, "Embedding API Key")

    # 4. Vision Configuration
    if not SystemConfigService.get_value("VISION_MODEL"):
        logger.info("Seeding VISION_MODEL from settings...")
        SystemConfigService.set_value("VISION_MODEL", "gpt-4o", "Vision Model Name (Multimodal)")

    # 5. HITL / Router Configuration
    if not SystemConfigService.get_value("INTENT_MIN_CONFIDENCE"):
        logger.info("Seeding INTENT_MIN_CONFIDENCE...")
        SystemConfigService.set_value("INTENT_MIN_CONFIDENCE", "0.35", "Intent Classifier Threshold (0.0-1.0)")


async def init_atlas_config() -> None:
    """Initialize Atlas configuration (Redis-based, no hardcoding)."""
    logger.info("Initializing Atlas configuration...")
    from app.core.atlas.config_manager import AtlasConfigManager
    await AtlasConfigManager.initialize_defaults()


async def init_mcp() -> None:
    logger.info("Initializing MCP configuration...")
    # Use the SQLAlchemy URI from settings
    db_url = str(settings.SQLALCHEMY_DATABASE_URI)

    # 1. Local Postgres (System Default)
    details_pg = {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres", db_url],
        "env": {},
    }
    try:
        await mcp_client_manager.add_server("local-postgres", details_pg)
        logger.info("MCP 'local-postgres' configured successfully.")
    except Exception as e:
        logger.error(f"Failed to configure local-postgres: {e}")

    # 2. Filesystem (Critical for Coder)
    # Allow access to PROJECTS_ROOT
    fs_args = [settings.PROJECTS_ROOT]
    details_fs = {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", *fs_args],
        "env": {},
    }
    try:
        await mcp_client_manager.add_server("filesystem", details_fs)
        logger.info(f"MCP 'filesystem' configured successfully for {settings.PROJECTS_ROOT}.")
    except Exception as e:
        logger.error(f"Failed to configure filesystem: {e}")

    # 2. Brave Search (Network Capability)
    brave_key = os.getenv("BRAVE_API_KEY")
    if brave_key:
        details_brave = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            "env": {"BRAVE_API_KEY": brave_key},
        }
        try:
            await mcp_client_manager.add_server("brave-search", details_brave)
            logger.info("MCP 'brave-search' configured successfully.")
        except Exception as e:
            logger.error(f"Failed to configure brave-search: {e}")
    else:
        logger.warning("BRAVE_API_KEY not found. Skipping 'brave-search' MCP auto-configuration.")


def main() -> None:
    logger.info("Creating initial data")
    init()

    # Run Async Init for MCP and Atlas
    async def async_init():
        await init_atlas_config()
        await init_mcp()

    try:
        asyncio.run(async_init())
    except Exception as e:
        logger.error(f"Async initialization failed: {e}")

    logger.info("Initial data created")


if __name__ == "__main__":
    main()
