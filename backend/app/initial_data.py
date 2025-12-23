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


async def init_mcp() -> None:
    logger.info("Initializing MCP configuration...")
    # Use the SQLAlchemy URI from settings
    db_url = str(settings.SQLALCHEMY_DATABASE_URI)

    details = {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres", db_url],
        "env": {},
    }

    try:
        # add_server will persist to DB and try to connect
        await mcp_client_manager.add_server("local-postgres", details)
        logger.info("MCP 'local-postgres' configured successfully.")
    except Exception as e:
        logger.error(f"Failed to configure MCP server: {e}")


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
