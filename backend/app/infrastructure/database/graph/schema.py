"""
Centralized Graph Schema Management for EvoLoop.
Handles creation of indexes and constraints across all domains.
"""

import logging

from app.core.config import settings
from app.infrastructure.database.graph.driver import GraphManager, IGraphDriver

logger = logging.getLogger(__name__)


class GraphSchemaManager:
    """
    Manages Neo4j indexes and constraints to ensure data integrity
    and query performance.
    """

    def __init__(self, driver: IGraphDriver | None = None):
        self._driver = driver

    async def initialize(self) -> None:
        """Initialize all required indexes and constraints."""
        driver = self._driver or GraphManager.get_driver()
        
        # In FileGraph mode, we don't need to create indexes/constraints explicitly
        # but we check connectivity.
        if not await driver.verify_connectivity():
            logger.warning("[GraphSchema] Driver not connected, skipping schema initialization")
            return

        async with driver.session() as session:
            # 1. Memory Domain
            await self._create_constraint(session, "memory_id", "Memory", "id")
            await self._create_index(session, "memory_project", "Memory", "project_id")
            await self._create_index(session, "memory_type", "Memory", "type")
            await self._create_index(session, "memory_source", "Memory", "source_message_id")
            
            # 2. Codebase Domain
            await self._create_constraint(session, "file_path", "File", "path")
            await self._create_index(session, "file_project", "File", "project_id")
            await self._create_index(session, "code_entity_name", "CodeEntity", "name")
            await self._create_index(session, "code_entity_project", "CodeEntity", "project_id")
            await self._create_index(session, "directory_path", "Directory", "path")
            await self._create_index(session, "directory_project", "Directory", "project_id")
            
            # 3. Atlas Domain
            await self._create_constraint(session, "atlas_app_bundle", "App", "bundle_id")
            await self._create_constraint(session, "atlas_state_id", "State", "state_id")
            
            # 4. Concept Domain (Unified)
            await self._create_constraint(session, "concept_id", "Concept", "id")
            await self._create_index(session, "concept_name", "Concept", "name")
            await self._create_index(session, "concept_title", "Concept", "title")
            await self._create_index(session, "concept_project", "Concept", "project_id")
            
            # 5. Vector Indexes (Conditional)
            if hasattr(settings, "EMBEDDING_DIMENSIONS"):
                dimensions = int(settings.EMBEDDING_DIMENSIONS)
                await self._create_vector_index(session, "concept_embeddings", "Concept", "embedding", dimensions)

            logger.info("[GraphSchema] ✓ All indexes and constraints verified")

    async def _create_constraint(self, session, name: str, label: str, prop: str):
        """Create a uniqueness constraint if it doesn't exist."""
        query = f"CREATE CONSTRAINT {name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
        await session.run(query)

    async def _create_index(self, session, name: str, label: str, prop: str):
        """Create a range index if it doesn't exist."""
        query = f"CREATE INDEX {name} IF NOT EXISTS FOR (n:{label}) ON (n.{prop})"
        await session.run(query)

    async def _create_vector_index(self, session, name: str, label: str, prop: str, dimensions: int):
        """Create a vector index if it doesn't exist."""
        query = f"""
            CREATE VECTOR INDEX {name} IF NOT EXISTS
            FOR (n:{label}) ON (n.{prop})
            OPTIONS {{indexConfig: {{
                `vector.dimensions`: {dimensions},
                `vector.similarity_function`: 'cosine'
            }}}}
        """
        await session.run(query)


# Global Instance
schema_manager = GraphSchemaManager()
