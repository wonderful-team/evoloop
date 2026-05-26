"""
Graph Memory Storage Backend
============================

Full-mode storage backend using a graph database.
Supports hierarchical relationships and complex traversals.

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

from app.infrastructure.database.graph.driver import GraphManager
HAS_GRAPH = True # Graph dependency is now handled by infrastructure

logger = logging.getLogger(__name__)


class GraphMemoryStorage(IMemoryStorage):
    """
    Graph-based memory storage backend.
    
    Works with any IGraphDriver (e.g., Neo4j, In-Memory Graph).
    """

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        """
        Initialize graph storage.
        """
        self._driver: Any = None

        logger.info("GraphMemoryStorage initialized")

    # ==========================================================================
    # IMemoryStorage Lifecycle Methods
    # ==========================================================================

    async def initialize(self) -> None:
        """
        Initialize graph connection.
        """
        try:
            self._driver = GraphManager.get_driver()
            
            # Verify connectivity
            await self._driver.verify_connectivity()

            # Initialize Schema via centralized manager
            from app.infrastructure.database.graph.schema import schema_manager
            await schema_manager.initialize()

            logger.info("Graph storage initialized and connected")

        except Exception as e:
            raise StorageConnectionError(f"Failed to connect to graph: {e}")

    async def _create_schema(self) -> None:
        """Deprecated: Schema is now managed by GraphSchemaManager."""
        pass

    async def close(self) -> None:
        """Close graph connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Graph storage connection closed")

    async def truncate_all(self) -> None:
        """Clear all memory data."""
        if not self._driver:
            return

        await self._driver.delete_nodes("Memory")
        await self._driver.delete_nodes("Concept")
        logger.warning("Graph storage truncated")

    async def flush(self) -> None:
        """Alias for truncate_all."""
        await self.truncate_all()

    async def health_check(self) -> "StorageHealthCheck":
        """Check health status."""
        if not self._driver:
            return StorageHealthCheck(status="not_initialized", backend="GraphMemoryStorage")

        try:
            nodes = await self._driver.find_nodes("Memory", limit=1)
            return StorageHealthCheck(
                status="healthy",
                backend="GraphMemoryStorage",
                entry_count=len(nodes), # Simple check
            )
        except Exception as e:
            return StorageHealthCheck(
                status="unhealthy",
                backend="GraphMemoryStorage",
                error=str(e),
            )

    # ==========================================================================
    # IMemoryStorage CRUD Operations
    # ==========================================================================

    async def save(self, entry: MemoryEntry) -> None:
        """Save a memory entry using high-level API."""
        if not self._driver:
            raise StorageError("Graph driver not initialized.")

        # Update timestamp
        entry.updated_at = datetime.utcnow()

        # Determine Label: type 'concept' uses 'Concept', others use 'Memory'
        label = "Concept" if entry.type == MemoryType.CONCEPT else "Memory"
        
        # Prepare properties
        props = entry.model_dump()
        props["created_at"] = entry.created_at.isoformat()
        props["updated_at"] = entry.updated_at.isoformat()
        if props.get("extra"):
            props["extra"] = str(props["extra"]) # Simple serialization for now

        await self._driver.upsert_node(label, "id", props)
        logger.debug(f"Saved memory {entry.id} as {label}")

    async def get(self, entry_id: str) -> MemoryEntry | None:
        """Get a memory entry by ID."""
        if not self._driver:
            raise StorageError("Graph driver not initialized.")

        # Search across both Memory and Concept
        for label in ["Memory", "Concept"]:
            nodes = await self._driver.find_nodes(label, {"id": entry_id}, limit=1)
            if nodes:
                return self._node_to_entry(nodes[0])
        return None

    async def find_by_hash(self, content_hash: str, project_id: int | None = None) -> MemoryEntry | None:
        """Find a memory entry by its content hash."""
        if not self._driver:
            raise StorageError("Graph driver not initialized.")

        filters = {"content_hash": content_hash}
        if project_id is not None:
            filters["project_id"] = project_id

        for label in ["Memory", "Concept"]:
            nodes = await self._driver.find_nodes(label, filters, limit=1)
            if nodes:
                return self._node_to_entry(nodes[0])
        return None

    async def delete(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        if not self._driver:
            raise StorageError("Graph driver not initialized.")

        deleted = await self._driver.delete_nodes("Memory", {"id": entry_id})
        if not deleted:
            deleted = await self._driver.delete_nodes("Concept", {"id": entry_id})
            
        return deleted > 0

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
        """Search memory entries using high-level API."""
        if not self._driver:
            raise StorageError("Graph driver not initialized.")

        # Note: True text search still requires Cypher or Vector search.
        # Here we use a simpler 'find_nodes' which might be limited.
        
        all_results = []
        for label in ["Memory", "Concept"]:
            # Combine filters
            search_filters = filters or {}
            if privacy:
                search_filters["privacy"] = privacy.value
            if project_id is not None:
                search_filters["project_id"] = project_id
            
            nodes = await self._driver.find_nodes(label, search_filters, limit=limit)
            
            # Post-filter for text query if present (since find_nodes is equality based)
            for node in nodes:
                if query and query.lower() not in str(node).lower():
                    continue
                all_results.append(self._node_to_entry(node))
        
        return all_results[:limit]

    async def list_all(
        self,
        type_filter: MemoryType | None = None,
        privacy_filter: PrivacyLevel | None = None,
        project_id: int | None = None,
        limit: int | None = None,
        member_id: int = 0,
    ) -> list[MemorySearchResult]:
        """List memories using high-level API."""
        if not self._driver:
            raise StorageError("Graph driver not initialized.")

        filters = {}
        if type_filter:
            filters["type"] = type_filter.value
        if privacy_filter:
            filters["privacy"] = privacy_filter.value
        if project_id is not None:
            filters["project_id"] = project_id

        results = []
        for label in ["Memory", "Concept"]:
            nodes = await self._driver.find_nodes(label, filters, limit=limit or 100)
            for node in nodes:
                entry = self._node_to_entry(node)
                if entry:
                    results.append(entry.to_search_result())
        
        return results[:limit] if limit else results

    async def get_multi(self, entry_ids: list[str]) -> dict[str, MemoryEntry]:
        """Batch retrieve entries."""
        if not self._driver or not entry_ids:
            return {}

        results = {}
        for entry_id in entry_ids:
            entry = await self.get(entry_id)
            if entry:
                results[entry.id] = entry
        return results

    async def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        project_id: int | None = None,
    ) -> list[MemoryEntry]:
        """
        Vector similarity search in graph.
        """
        if not self._driver:
            return []

        filters = {"project_id": project_id} if project_id is not None else None
        
        # We search Concepts or Memories (Episodes)
        # For simplicity, we search Concept first as they are usually the entry points.
        nodes = await self._driver.search_similar(
            "Concept", 
            query_embedding, 
            top_k=top_k, 
            filters=filters
        )
        
        results = []
        for n in nodes:
            entry = self._node_to_entry(n)
            if entry:
                results.append(entry)
        
        return results

    async def get_related(
        self,
        entry_id: str,
        relation_type: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Get related memories via graph traversal."""
        if not self._driver:
            raise StorageError("Graph driver not initialized.")

        # Traverse RELATED_TO
        nodes = await self._driver.traverse(
            "Memory", {"id": entry_id}, 
            rel_type=relation_type or "RELATED_TO",
            target_label="Memory",
            limit=limit
        )
        return [self._node_to_entry(n) for n in nodes if n]

    async def get_recent(self, count: int = 5, project_id: int | None = None) -> list[MemoryEntry]:
        """Get most recently updated memories."""
        if not self._driver:
            raise StorageError("Graph driver not initialized.")

        all_entries = []
        for label in ["Memory", "Concept"]:
            filters = {}
            if project_id is not None:
                filters["project_id"] = project_id
            
            nodes = await self._driver.find_nodes(label, filters, limit=count)
            all_entries.extend([self._node_to_entry(n) for n in nodes if n])
            
        # Sort by updated_at
        all_entries.sort(key=lambda x: x.updated_at, reverse=True)
        return all_entries[:count]

    async def record_episode(self, episode: Any) -> str:
        """Record an execution episode using high-level API."""
        if not self._driver:
            raise StorageError("Graph driver not initialized.")

        entry_id = f"ep_{episode.source_message_id or datetime.utcnow().timestamp()}"
        props = {
            "id": entry_id,
            "type": "episode",
            "title": f"Episode: {episode.goal[:50]}...",
            "content": f"Goal: {episode.goal}\nResult: {episode.result}",
            "project_id": episode.project_id,
            "source_message_id": episode.source_message_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "privacy": "team"
        }
        await self._driver.upsert_node("Memory", "id", props)
        return entry_id

    async def link_concept_to_episode(self, concept_name: str, episode_id: str) -> None:
        """Link a concept to an episode."""
        if not self._driver:
            return
        
        # Link Concept to Memory (Episode)
        # Note: We match by title for concept
        await self._driver.link_nodes(
            "Concept", {"title": concept_name},
            "Memory", {"id": episode_id},
            "LINKED_TO"
        )

    async def find_episodes_by_concept(self, concept_name: str, limit: int = 10) -> list[dict[str, Any]]:
        """Find episodes linked to a concept."""
        if not self._driver:
            return []
            
        nodes = await self._driver.traverse(
            "Concept", {"title": concept_name},
            rel_type="LINKED_TO",
            target_label="Memory",
            limit=limit
        )
        
        return [{
            "id": n["id"],
            "goal": n["title"],
            "result": n["content"],
            "timestamp": n.get("created_at")
        } for n in nodes if n]

    async def get_all_concept_counts(self) -> dict[str, int]:
        """
        Get counts of episodes. 
        """
        if not self._driver:
            return {}
        
        # fallback to raw query for aggregation
        query = """
        MATCH (c)-[:LINKED_TO]->(e:Memory)
        WHERE (c:Memory OR c:Concept) AND c.type = 'concept'
        RETURN c.title as name, count(e) as count
        """
        records = await self._driver.execute_query(query)
        return {r["name"]: r["count"] for r in records}

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    def _node_to_entry(self, node: dict[str, Any]) -> MemoryEntry | None:
        """Convert graph node to MemoryEntry."""
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
