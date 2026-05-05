"""
Neo4j Memory Storage Backend

Full-mode storage backend using Neo4j graph database.
Implements IMemoryStorage interface independently (not inheriting from FileMemoryStorage).

Features:
- Graph-based memory relationships
- Vector similarity search (with embeddings)
- Project-based memory organization
- Semantic search capabilities
"""

import logging
from datetime import datetime
from typing import Any

from app.core.memory.interfaces.storage import (
    IMemoryStorage,
    StorageConnectionError,
    StorageError,
    StorageHealthCheck,
)
from app.core.memory.models import (
    MemoryEntry,
    MemorySearchResult,
    MemoryType,
    PrivacyLevel,
    MemoryTier,
)

# Optional Neo4j import
try:
    from neo4j import AsyncGraphDatabase

    from app.infrastructure.database.graph.driver import get_graph_db
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False

logger = logging.getLogger(__name__)


class Neo4jMemoryStorage(IMemoryStorage):
    """
    Neo4j-based memory storage backend.
    
    Independent implementation of IMemoryStorage using Neo4j graph database.
    Supports graph relationships and vector similarity search.
    
    Note: This is a foundational implementation. Some advanced features
    (vector search, graph relationships) are prepared but require
    additional setup (embeddings, indexes).
    """

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        """
        Initialize Neo4j storage.
        
        Args:
            uri: Neo4j connection URI (e.g., "bolt://localhost:7687")
            user: Neo4j username
            password: Neo4j password
            
        Note:
            If parameters not provided, will attempt to use configured defaults.
        """
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = None

        if not HAS_NEO4J:
            logger.warning("Neo4j driver not available. Neo4jMemoryStorage will not function.")
            raise StorageError(
                "Neo4j driver not installed. "
                "Install with: pip install neo4j"
            )

        logger.info("Neo4jMemoryStorage initialized (connection deferred)")

    # ==========================================================================
    # IMemoryStorage Lifecycle Methods
    # ==========================================================================

    async def initialize(self) -> None:
        """
        Initialize Neo4j connection and schema.
        
        Creates necessary indexes and constraints.
        """
        if not HAS_NEO4J:
            raise StorageError("Neo4j driver not available")

        try:
            # Get driver from configured source or create new
            if self._uri:
                self._driver = AsyncGraphDatabase.driver(
                    self._uri,
                    auth=(self._user, self._password) if self._user else None,
                )
            else:
                self._driver = await get_graph_db()

            # Verify connectivity
            await self._driver.verify_connectivity()

            # Create schema (indexes and constraints)
            await self._create_schema()

            logger.info("Neo4j storage initialized and connected")

        except Exception as e:
            raise StorageConnectionError(f"Failed to connect to Neo4j: {e}")

    async def _create_schema(self) -> None:
        """Create Neo4j schema (indexes and constraints)."""
        if not self._driver:
            return

        async with self._driver.session() as session:
            # Create constraints
            constraints = [
                "CREATE CONSTRAINT memory_id IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE",
                "CREATE INDEX memory_project IF NOT EXISTS FOR (m:Memory) ON (m.project_id)",
                "CREATE INDEX memory_type IF NOT EXISTS FOR (m:Memory) ON (m.type)",
                "CREATE INDEX memory_privacy IF NOT EXISTS FOR (m:Memory) ON (m.privacy)",
            ]

            for constraint in constraints:
                try:
                    await session.run(constraint)
                except Exception as e:
                    logger.warning(f"Schema creation warning (may already exist): {e}")

    async def close(self) -> None:
        """Close Neo4j connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j storage connection closed")

    async def flush(self) -> None:
        """
        Clear all memory data (for testing).
        
        WARNING: This deletes ALL memory nodes!
        """
        if not self._driver:
            return

        async with self._driver.session() as session:
            await session.run("MATCH (m:Memory) DETACH DELETE m")
            logger.warning("Neo4j storage flushed (all memory nodes deleted)")

    async def health_check(self) -> "StorageHealthCheck":
        """Check Neo4j health status."""
        if not self._driver:
            return StorageHealthCheck(status="not_initialized", backend="Neo4jMemoryStorage")

        try:
            async with self._driver.session() as session:
                result = await session.run("MATCH (m:Memory) RETURN count(m) as count")
                record = await result.single()
                count = record["count"] if record else 0

                return StorageHealthCheck(
                    status="healthy",
                    backend="Neo4jMemoryStorage",
                    entry_count=count,
                )
        except Exception as e:
            return StorageHealthCheck(
                status="unhealthy",
                backend="Neo4jMemoryStorage",
                error=str(e),
            )

    # ==========================================================================
    # IMemoryStorage CRUD Operations
    # ==========================================================================

    async def save(self, entry: MemoryEntry) -> None:
        """
        Save a memory entry to Neo4j.
        
        Creates or updates a Memory node with all properties.
        """
        if not self._driver:
            raise StorageError("Neo4j not initialized. Call initialize() first.")

        async with self._driver.session() as session:
            # Update timestamp
            entry.updated_at = datetime.utcnow()

            query = """
            MERGE (m:Memory {id: $id})
            SET m.type = $type,
                m.privacy = $privacy,
                m.title = $title,
                m.content = $content,
                m.description = $description,
                m.project_id = $project_id,
                m.user_id = $user_id,
                m.tags = $tags,
                m.source = $source,
                m.source_message_id = $source_message_id,
                m.content_hash = $content_hash,
                m.confidence = $confidence,
                m.version = $version,
                m.created_at = $created_at,
                m.updated_at = $updated_at
            RETURN m
            """

            await session.run(
                query,
                id=entry.id,
                type=entry.type.value,
                privacy=entry.privacy.value,
                title=entry.title,
                content=entry.content,
                description=entry.description,
                project_id=entry.project_id,
                user_id=entry.user_id,
                tags=entry.tags,
                source=entry.source,
                source_message_id=entry.source_message_id,
                content_hash=entry.content_hash,
                confidence=entry.confidence,
                version=entry.version,
                created_at=entry.created_at.isoformat(),
                updated_at=entry.updated_at.isoformat(),
            )

            logger.debug(f"Saved memory {entry.id} to Neo4j")

    async def get(self, entry_id: str) -> MemoryEntry | None:
        """Get a memory entry by ID from Neo4j."""
        if not self._driver:
            raise StorageError("Neo4j not initialized. Call initialize() first.")

        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (m:Memory {id: $id}) RETURN m",
                id=entry_id,
            )
            record = await result.single()

            if not record:
                return None

            node = record["m"]
            return self._node_to_entry(node)

    async def find_by_hash(self, content_hash: str, project_id: int | None = None) -> MemoryEntry | None:
        """Find a memory entry by its content hash to prevent duplication."""
        if not self._driver:
            raise StorageError("Neo4j not initialized.")

        async with self._driver.session() as session:
            query = "MATCH (m:Memory {content_hash: $hash}) "
            if project_id is not None:
                query += "WHERE m.project_id = $project_id "
            query += "RETURN m LIMIT 1"

            result = await session.run(query, hash=content_hash, project_id=project_id)
            record = await result.single()
            if record:
                return self._node_to_entry(record["m"])
            return None

    async def delete(self, entry_id: str) -> bool:
        """Delete a memory entry from Neo4j."""
        if not self._driver:
            raise StorageError("Neo4j not initialized. Call initialize() first.")

        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (m:Memory {id: $id}) DETACH DELETE m RETURN count(m) as deleted",
                id=entry_id,
            )
            record = await result.single()
            deleted = record["deleted"] if record else 0

            if deleted > 0:
                logger.debug(f"Deleted memory {entry_id} from Neo4j")
                return True
            return False

    # ==========================================================================
    # IMemoryStorage Query Operations
    # ==========================================================================

    async def search(
        self,
        query: str,
        types: list[MemoryType] | None = None,
        privacy: PrivacyLevel | None = None,
        project_id: int | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """
        Search memory entries in Neo4j.
        
        Currently uses keyword matching. Vector similarity can be added
        when embeddings are configured.
        """
        if not self._driver:
            raise StorageError("Neo4j not initialized. Call initialize() first.")

        async with self._driver.session() as session:
            # Build query with filters
            where_clauses = []
            params = {"limit": limit}

            # Text search (case-insensitive) - only if query is not empty
            if query and query.strip():
                params["query"] = query.lower()
                where_clauses.append(
                    "(toLower(m.title) CONTAINS $query OR toLower(m.content) CONTAINS $query OR toLower(m.description) CONTAINS $query)"
                )

            # Metadata filters
            if filters:
                for k, v in filters.items():
                    param_name = f"filter_{k}"
                    where_clauses.append(f"m.{k} = ${param_name}")
                    params[param_name] = v

            # Type filter
            if types:
                type_values = [t.value for t in types]
                where_clauses.append("m.type IN $types")
                params["types"] = type_values

            # Privacy filter
            if privacy:
                where_clauses.append("m.privacy = $privacy")
                params["privacy"] = privacy.value

            # Project filter
            if project_id is not None:
                where_clauses.append("(m.project_id = $project_id OR m.project_id IS NULL)")
                params["project_id"] = project_id

            # Structured filters (metadata)
            if filters:
                for k, v in filters.items():
                    param_name = f"filter_{k}"
                    where_clauses.append(f"m.{k} = ${param_name}")
                    params[param_name] = v

            where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"

            cypher = f"""
            MATCH (m:Memory)
            WHERE {where_clause}
            RETURN m
            ORDER BY m.updated_at DESC
            LIMIT $limit
            """

            result = await session.run(cypher, **params)
            records = await result.data()

            entries = []
            for record in records:
                entry = self._node_to_entry(record["m"])
                if entry:
                    entries.append(entry)

            return entries

    async def list_all(
        self,
        type_filter: MemoryType | None = None,
        privacy_filter: PrivacyLevel | None = None,
        project_id: int | None = None,
        limit: int | None = None,
    ) -> list[MemorySearchResult]:
        """List memories (lightweight) with project and type filtering."""
        if not self._driver:
            raise StorageError("Neo4j not initialized. Call initialize() first.")

        async with self._driver.session() as session:
            where_clauses = []
            params = {}

            if type_filter:
                where_clauses.append("m.type = $type")
                params["type"] = type_filter.value

            if privacy_filter:
                where_clauses.append("m.privacy = $privacy")
                params["privacy"] = privacy_filter.value
            
            if project_id is not None:
                where_clauses.append("m.project_id = $project_id")
                params["project_id"] = project_id

            where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"

            cypher = f"""
            MATCH (m:Memory)
            WHERE {where_clause}
            RETURN m.id as id, m.title as title, m.description as description,
                   m.type as type, m.tier as tier, m.utility_score as utility_score,
                   m.confidence as confidence, m.updated_at as updated_at
            ORDER BY m.updated_at DESC
            {f"LIMIT $limit" if limit else ""}
            """
            if limit:
                params["limit"] = limit

            result = await session.run(cypher, **params)
            records = await result.data()

            results = []
            for record in records:
                # Parse updated_at carefully from ISO format (stored as string in Neo4j typically)
                ts = record["updated_at"]
                dt = datetime.fromisoformat(ts) if isinstance(ts, str) else datetime.utcnow()

                results.append(
                    MemorySearchResult(
                        id=record["id"],
                        title=record["title"],
                        description=record.get("description", ""),
                        type=MemoryType(record["type"]),
                        tier=MemoryTier(record.get("tier", "operational")),
                        utility_score=record.get("utility_score", 0.0),
                        confidence=record.get("confidence", 1.0),
                        updated_at=dt,
                    )
                )

            return results

    # ==========================================================================
    # IMemoryStorage Advanced Operations
    # ==========================================================================

    async def get_multi(self, entry_ids: list[str]) -> dict[str, MemoryEntry]:
        """Batch retrieve memory entries from Neo4j (O(1) roundtrip)."""
        if not self._driver or not entry_ids:
            return {}

        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (m:Memory) WHERE m.id IN $ids RETURN m",
                ids=entry_ids
            )
            records = await result.data()
            entries = {}
            for record in records:
                entry = self._node_to_entry(record["m"])
                if entry:
                    entries[entry.id] = entry
            return entries

    async def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        project_id: int | None = None,
    ) -> list[MemoryEntry]:
        """
        Vector similarity search.
        
        Note: This requires:
        1. Neo4j GDS library or vector index
        2. Embeddings stored on memory nodes
        3. Proper vector index configuration
        
        Currently raises NotImplementedError until fully configured.
        """
        # TODO: Implement when embeddings and vector index are ready
        raise NotImplementedError(
            "Vector search requires Neo4j GDS and pre-computed embeddings. "
            "Use text search (search()) as fallback."
        )

    async def get_related(
        self,
        entry_id: str,
        relation_type: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """
        Get related memories via graph traversal.
        
        This is where Neo4j shines - finding related memories through
        explicit relationships rather than text similarity.
        """
        if not self._driver:
            raise StorageError("Neo4j not initialized. Call initialize() first.")

        async with self._driver.session() as session:
            # For now, return memories from same project as "related"
            # TODO: Implement explicit relationship tracking

            query = """
            MATCH (m:Memory {id: $entry_id})
            OPTIONAL MATCH (m)-[:RELATED_TO]->(related:Memory)
            WHERE related IS NOT NULL
            RETURN related
            LIMIT $limit
            """

            result = await session.run(query, entry_id=entry_id, limit=limit)
            records = await result.data()

            entries = []
            for record in records:
                if record["related"]:
                    entry = self._node_to_entry(record["related"])
                    if entry:
                        entries.append(entry)

            return entries

    async def get_recent(self, count: int = 5) -> list[MemoryEntry]:
        """Get most recently updated memories from Neo4j."""
        if not self._driver:
            raise StorageError("Neo4j not initialized.")

        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (m:Memory)
                RETURN m
                ORDER BY m.updated_at DESC
                LIMIT $count
                """,
                count=count,
            )
            records = await result.data()
            return [self._node_to_entry(record["m"]) for record in records if record["m"]]

    async def record_episode(self, episode: Any) -> str:
        """
        Record an execution episode in the graph.
        episode: Episode object (pydantic model).
        """
        if not self._driver:
            raise StorageError("Neo4j not initialized.")

        # Convert Episode to MemoryEntry for standard storage
        entry_id = f"ep_{episode.source_message_id or datetime.utcnow().timestamp()}"
        
        async with self._driver.session() as session:
            # 1. Create Episode Node (using regular Memory label for consistency)
            query = """
            MERGE (m:Memory {id: $id})
            SET m.type = 'episode',
                m.title = $title,
                m.content = $content,
                m.project_id = $project_id,
                m.source_message_id = $source_message_id,
                m.created_at = $created_at,
                m.updated_at = $updated_at,
                m.privacy = 'team'
            RETURN m.id as entry_id
            """
            result = await session.run(
                query,
                id=entry_id,
                title=f"Episode: {episode.goal[:50]}...",
                content=f"Goal: {episode.goal}\nResult: {episode.result}",
                project_id=episode.project_id,
                source_message_id=episode.source_message_id,
                created_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat(),
            )
            record = await result.single()
            return record["entry_id"] if record else entry_id

    async def link_concept_to_episode(self, concept_name: str, episode_id: str) -> None:
        """Create a LINKED_TO relationship in Neo4j."""
        if not self._driver:
            return
        
        async with self._driver.session() as session:
            query = """
            MATCH (c:Memory {title: $concept_name})
            MATCH (e:Memory {id: $episode_id})
            MERGE (c)-[:LINKED_TO]->(e)
            """
            await session.run(query, concept_name=concept_name, episode_id=episode_id)
            logger.info(f"[Neo4jStorage] Linked concept '{concept_name}' to episode {episode_id}")

    async def find_episodes_by_concept(self, concept_name: str, limit: int = 10) -> list[dict]:
        """Find episodes linked to a concept via relationships."""
        if not self._driver:
            return []
            
        async with self._driver.session() as session:
            query = """
            MATCH (c:Memory {title: $concept_name})-[:LINKED_TO]->(e:Memory)
            RETURN e
            ORDER BY e.updated_at DESC
            LIMIT $limit
            """
            result = await session.run(query, concept_name=concept_name, limit=limit)
            records = await result.data()
            
            results = []
            for record in records:
                node = record["e"]
                results.append({
                    "id": node["id"],
                    "goal": node["title"],
                    "result": node["content"],
                    "timestamp": node["created_at"]
                })
            return results

    async def get_all_concept_counts(self) -> dict[str, int]:
        """Get counts of episodes linked to each concept using graph aggregation."""
        if not self._driver:
            return {}
            
        async with self._driver.session() as session:
            query = """
            MATCH (c:Memory {type: 'concept'})-[:LINKED_TO]->(e:Memory)
            RETURN c.title as name, count(e) as count
            """
            result = await session.run(query)
            records = await result.data()
            return {r["name"]: r["count"] for r in records}

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    def _node_to_entry(self, node: Any) -> MemoryEntry | None:
        """Convert Neo4j node to MemoryEntry."""
        try:
            from datetime import datetime

            return MemoryEntry(
                id=node["id"],
                type=MemoryType(node["type"]),
                privacy=PrivacyLevel(node["privacy"]),
                title=node["title"],
                content=node["content"],
                description=node.get("description", ""),
                project_id=node.get("project_id"),
                user_id=node.get("user_id"),
                tags=node.get("tags", []),
                source=node.get("source", "manual"),
                source_message_id=node.get("source_message_id"),
                confidence=node.get("confidence", 1.0),
                version=node.get("version", 1),
                created_at=datetime.fromisoformat(node["created_at"]),
                updated_at=datetime.fromisoformat(node["updated_at"]),
            )
        except Exception as e:
            logger.warning(f"Failed to convert node to entry: {e}")
            return None
