import asyncio
from neo4j import AsyncGraphDatabase

from app.core.config import settings
from app.logging import logger


class Neo4jManager:
    _drivers: dict[asyncio.AbstractEventLoop, AsyncGraphDatabase] = {}

    @classmethod
    def get_driver(cls):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("Cannot get Neo4j driver without a running event loop")

        # Check existing driver for this loop
        if loop in cls._drivers:
            driver = cls._drivers[loop]
            # Simple check if driver is potentially usable (Neo4j driver doesn't have open() method,
            # but we trust our cache unless explicitly closed)
            return driver

        # Create new driver bound to this loop
        try:
            driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            # No explicit 'open', but verifying connectivity is good practice
            # await driver.verify_connectivity() # This is async, can't do in sync method.
            # Lazy connect is fine.
            
            cls._drivers[loop] = driver
            logger.info(f"Connected to Neo4j (Loop: {id(loop)})")
            return driver
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise

    @classmethod
    async def close_driver(cls):
        """Close driver for current loop"""
        try:
            loop = asyncio.get_running_loop()
            if loop in cls._drivers:
                driver = cls._drivers.pop(loop)
                await driver.close()
                logger.info(f"Closed Neo4j connection (Loop: {id(loop)})")
        except RuntimeError:
            pass
            
    @classmethod
    async def close_all(cls):
        """Close drivers for all loops (e.g. shutdown)"""
        for loop, driver in cls._drivers.items():
            try:
                await driver.close()
            except Exception as e:
                logger.warning(f"Error closing Neo4j driver for loop {id(loop)}: {e}")
        cls._drivers.clear()


async def get_graph_db():
    driver = Neo4jManager.get_driver()
    return driver
