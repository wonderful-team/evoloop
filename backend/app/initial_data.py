import asyncio
import logging
import os

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
    from app.core.system import SystemConfigService

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

    # 4. Agent-S (Micro-Skill)
    # We use the internal docker DNS 'skill-agent-s'
    # Default port 8000 mapped internally
    agent_s_url = "http://skill-agent-s:8000/sse"
    details_agent_s = {
        "command": agent_s_url,  # Command is URL for SSE
        "args": [],
        "env": {},
    }
    try:
        # We add it but it might fail if container is not up yet - MCP Client handles reconnection/retry?
        # mcp_client.add_server will try to connect. If fail, it should still add to DB?
        # Our implementation of add_server tries to connect and logs error if fails, but adds to DB?
        # Let's check add_server implementation... it adds to DB first! So it's safe.
        await mcp_client_manager.add_server("skill-agent-s", details_agent_s)
        logger.info("MCP 'skill-agent-s' configured successfully.")
    except Exception as e:
        logger.info(f"Configuration created for 'skill-agent-s' (Connection pending): {e}")

    # 5. Browser-Use (Micro-Skill)
    browser_use_url = "http://skill-browser-use:8000/sse"
    details_browser = {
        "command": browser_use_url,
        "args": [],
        "env": {}
    }
    try:
        await mcp_client_manager.add_server("skill-browser-use", details_browser)
        logger.info("MCP 'skill-browser-use' configured successfully.")
    except Exception as e:
        logger.info(f"Configuration created for 'skill-browser-use' (Connection pending): {e}")

    # 6. Open-AutoGLM (Micro-Skill)
    autoglm_url = "http://skill-open-autoglm:8000/sse"
    details_autoglm = {
        "command": autoglm_url,
        "args": [],
        "env": {}
    }
    try:
        await mcp_client_manager.add_server("skill-open-autoglm", details_autoglm)
        logger.info("MCP 'skill-open-autoglm' configured successfully.")
    except Exception as e:
        logger.info(f"Configuration created for 'skill-open-autoglm' (Connection pending): {e}")

    # 7. Crawl4AI (Micro-Skill)
    crawl4ai_url = "http://skill-crawl4ai:8000/sse"
    details_crawl = {
        "command": crawl4ai_url,
        "args": [],
        "env": {}
    }
    try:
        await mcp_client_manager.add_server("skill-crawl4ai", details_crawl)
        logger.info("MCP 'skill-crawl4ai' configured successfully.")
    except Exception as e:
        logger.info(f"Configuration created for 'skill-crawl4ai' (Connection pending): {e}")


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
