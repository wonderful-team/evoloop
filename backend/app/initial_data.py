import asyncio
import logging

from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine, init_db
from app.infrastructure.mcp.client import mcp_client_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init() -> None:
    with Session(engine) as session:
        init_db(session)
        
    # Seed System Configuration from Environment/Settings
    # This ensures that on first run, the database is populated with valid defaults
    from app.domain.system.service import SystemConfigService
    
    # 1. PROJECTS_ROOT
    if not SystemConfigService.get_value("PROJECTS_ROOT"):
        default_root = settings.PROJECTS_ROOT
        logger.info(f"Seeding PROJECTS_ROOT from settings: {default_root}")
        SystemConfigService.set_value("PROJECTS_ROOT", default_root, "Root directory for project storage")
    
    # 2. IMAGICBOX_DEVICE_NAME
    if not SystemConfigService.get_value("IMAGICBOX_DEVICE_NAME"):
        default_name = settings.IMAGICBOX_DEVICE_NAME
        if default_name:
            logger.info(f"Seeding IMAGICBOX_DEVICE_NAME from settings: {default_name}")
            SystemConfigService.set_value("IMAGICBOX_DEVICE_NAME", default_name, "Device identifier for EvoLoop Link")


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

    # 2. Brave Search (Network Capability)
    import os
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

    # Run Async Init for MCP
    try:
        asyncio.run(init_mcp())
    except Exception as e:
        logger.error(f"Async initialization failed: {e}")

    logger.info("Initial data created")


if __name__ == "__main__":
    main()
