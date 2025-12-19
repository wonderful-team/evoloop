from neo4j import GraphDatabase, AsyncGraphDatabase
from app.core.config import settings
from app.logging import logger


class Neo4jManager:
    _driver = None

    @classmethod
    def get_driver(cls):
        if cls._driver is None:
            try:
                cls._driver = AsyncGraphDatabase.driver(
                    settings.NEO4J_URI, 
                    auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
                )
                logger.info("Connected to Neo4j")
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                raise
        return cls._driver

    @classmethod
    async def close_driver(cls):
        if cls._driver:
            await cls._driver.close()
            cls._driver = None
            logger.info("Closed Neo4j connection")


async def get_graph_db():
    driver = Neo4jManager.get_driver()
    return driver
