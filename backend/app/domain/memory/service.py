from app.infrastructure.database.graph.driver import get_graph_db
from app.logging import logger
from app.core.config import settings


class MemoryService:
    """
    Manages long-term memory in Neo4j.
    Stores User Preferences and Project Concepts.
    """

    async def initialize_schema(self):
        """Ensure indexes and constraints exist."""
        driver = await get_graph_db()
        async with driver.session() as session:
            # User Constraints
            await session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE")
            # Preference Constraints
            await session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Preference) REQUIRE p.key IS UNIQUE")
            # Concept Constraints
            await session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE")
            # Fulltext Index for Concepts (if supported, else simple lookup)
            try:
                await session.run("CREATE FULLTEXT INDEX concept_search IF NOT EXISTS FOR (c:Concept) ON EACH [c.name, c.description]")
            except Exception:
                logger.warning("Fulltext index creation failed (might already exist or not supported).")

    async def add_user_preference(self, user_id: str, key: str, value: str, description: str = ""):
        driver = await get_graph_db()
        query = """
        MERGE (u:User {id: $user_id})
        MERGE (p:Preference {key: $key})
        SET p.value = $value, p.description = $description
        MERGE (u)-[:PREFERS]->(p)
        RETURN p
        """
        async with driver.session() as session:
            await session.run(query, user_id=user_id, key=key, value=value, description=description)
            logger.info(f"Stored Preference: {key}={value}")

    async def get_user_preferences(self, user_id: str) -> str:
        driver = await get_graph_db()
        query = """
        MATCH (u:User {id: $user_id})-[:PREFERS]->(p:Preference)
        RETURN p.key as key, p.value as value, p.description as desc
        """
        async with driver.session() as session:
            result = await session.run(query, user_id=user_id)
            records = await result.data()

        if not records:
            return "No specific preferences recorded."

        lines = ["**User Preferences:**"]
        for r in records:
            lines.append(f"- {r['key']}: {r['value']} ({r['desc']})")
        return "\n".join(lines)

    async def add_concept(self, name: str, description: str, project_id: int, related_files: list[str] = None):
        driver = await get_graph_db()
        query = """
        MERGE (c:Concept {name: $name, project_id: $pid})
        SET c.description = $description, c.updated_at = timestamp()
        """
        async with driver.session() as session:
            await session.run(query, name=name, pid=project_id, description=description)

            if related_files:
                for file_path in related_files:
                    # We assume File nodes already exist from Indexer, but we use MERGE to be safe
                    file_query = """
                    MATCH (c:Concept {name: $name, project_id: $pid})
                    MERGE (f:File {path: $path})
                    MERGE (c)-[:REFERENCES]->(f)
                    """
                    await session.run(file_query, name=name, pid=project_id, path=file_path)
        logger.info(f"Stored Concept: {name} (Project {project_id})")

    async def search_concepts(self, query_text: str, project_id: int) -> str:
        driver = await get_graph_db()
        # Use fulltext index if available, else regex search
        # Note: Fulltext index is global. We filter AFTER matching or use WHERE clause if index supports it.
        # Simple approach: MATCH ... WHERE ...
        
        fallback_cypher = """
        MATCH (c:Concept)
        WHERE c.project_id = $pid AND (c.name CONTAINS $query OR c.description CONTAINS $query)
        RETURN c.name as name, c.description as desc
        LIMIT $limit
        """

        async with driver.session() as session:
            # For simplicity in this fix, we use the fallback logic which supports property filtering easily.
            # Fulltext index with property filter requires Neo4j 4.3+ or trickier query structure.
            result = await session.run(fallback_cypher, query=query_text, pid=project_id, limit=settings.MEMORY_SEARCH_LIMIT)
            records = await result.data()

        if not records:
            return "No relevant concepts found."

        lines = []
        for r in records:
            lines.append(f"- **{r['name']}**: {r['desc']}")
        return "\n".join(lines)


memory_service = MemoryService()
