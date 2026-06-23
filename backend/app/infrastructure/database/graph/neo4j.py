"""
Neo4j implementation of the Graph Driver.
"""

import logging
from typing import Any

from neo4j import AsyncGraphDatabase
from app.infrastructure.database.graph.driver import IGraphDriver

logger = logging.getLogger(__name__)

class Neo4jDriver(IGraphDriver):
    """
    Neo4j-specific implementation of the Graph Driver using the official async driver.
    """

    def __init__(self, uri: str, user: str, password: str | None):
        self._uri = uri
        self._auth = (user, password) if password else None
        self._driver = AsyncGraphDatabase.driver(self._uri, auth=self._auth)

    async def verify_connectivity(self) -> bool:
        """Verify the connection to Neo4j."""
        try:
            await self._driver.verify_connectivity()
            return True
        except Exception as e:
            logger.error(f"Neo4j connectivity check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the Neo4j driver."""
        await self._driver.close()

    def session(self) -> Any:
        """Return a Neo4j async session."""
        return self._driver.session()

    async def execute_query(self, query: str, parameters: dict | None = None, **kwargs) -> list[dict[str, Any]]:
        """
        Execute a raw Cypher query.
        For convenience, this handles session lifecycle automatically.
        """
        async with self.session() as session:
            result = await session.run(query, parameters, **kwargs)
            return await result.data()

    # --- High Level Agnostic API Implementation ---

    async def upsert_node(self, label: str, id_field: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Create or update a node using MERGE."""
        query = f"""
        MERGE (n:{label} {{{id_field}: $id}})
        SET n += $props
        RETURN n
        """
        id_val = properties.get(id_field)
        if not id_val:
            raise ValueError(f"Property '{id_field}' missing for upsert into {label}")
            
        async with self.session() as session:
            result = await session.run(query, id=id_val, props=properties)
            record = await result.single()
            return record["n"] if record else {}

    async def find_nodes(self, label: str, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Find nodes matching the given property filters."""
        where_clauses = []
        params = {"limit": limit}
        
        if filters:
            for i, (k, v) in enumerate(filters.items()):
                where_clauses.append(f"n.{k} = $p{i}")
                params[f"p{i}"] = v
                
        where_str = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        query = f"MATCH (n:{label}){where_str} RETURN n LIMIT $limit"
        
        async with self.session() as session:
            result = await session.run(query, **params)
            data = await result.data()
            return [record["n"] for record in data if "n" in record]

    async def delete_nodes(self, label: str, filters: dict[str, Any] | None = None, detach: bool = True) -> int:
        """Delete nodes matching filters."""
        where_clauses = []
        params = {}
        
        if filters:
            for i, (k, v) in enumerate(filters.items()):
                where_clauses.append(f"n.{k} = $p{i}")
                params[f"p{i}"] = v
                
        where_str = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        delete_op = "DETACH DELETE" if detach else "DELETE"
        query = f"MATCH (n:{label}){where_str} {delete_op} n RETURN count(n) as deleted"
        
        async with self.session() as session:
            result = await session.run(query, **params)
            record = await result.single()
            return record["deleted"] if record else 0

    async def link_nodes(
        self,
        src_label: str,
        src_filters: dict,
        tgt_label: str,
        tgt_filters: dict,
        rel_type: str,
        rel_props: dict[str, Any] | None = None,
    ) -> bool:
        """Create a relationship between two sets of nodes."""
        # This is a bit complex as we need to match both sets
        query = f"""
        MATCH (s:{src_label}), (t:{tgt_label})
        WHERE {" AND ".join([f"s.{k} = $s_{k}" for k in src_filters.keys()])}
          AND {" AND ".join([f"t.{k} = $t_{k}" for k in tgt_filters.keys()])}
        MERGE (s)-[r:{rel_type}]->(t)
        SET r += $r_props
        RETURN count(r) as linked
        """
        params = {
            **{f"s_{k}": v for k, v in src_filters.items()},
            **{f"t_{k}": v for k, v in tgt_filters.items()},
            "r_props": rel_props or {}
        }
        
        async with self.session() as session:
            result = await session.run(query, **params)
            record = await result.single()
            return (record["linked"] > 0) if record else False

    async def traverse(
        self,
        start_label: str,
        start_filters: dict,
        rel_type: str,
        target_label: str | None = None,
        direction: str = "out",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Traverse the graph following relationships."""
        rel_pattern = f"-[:{rel_type}]->" if direction == "out" else f"<-[:{rel_type}]-"
        target_pattern = f"(target:{target_label})" if target_label else "(target)"
        
        query = f"""
        MATCH (s:{start_label}){rel_pattern}{target_pattern}
        WHERE {" AND ".join([f"s.{k} = $s_{k}" for k in start_filters.keys()])}
        RETURN target
        LIMIT $limit
        """
        params = {
            **{f"s_{k}": v for k, v in start_filters.items()},
            "limit": limit
        }
        
        async with self.session() as session:
            result = await session.run(query, **params)
            data = await result.data()
            return [record["target"] for record in data if "target" in record]

    async def search_similar(
        self,
        label: str,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Perform a vector similarity search in Neo4j (delegates to VectorStore for Concepts)."""
        
        if label == "Concept":
            from app.infrastructure.database.vector import get_vector_store
            vector_store = get_vector_store()
            
            # 1. Search in unified vector store
            vec_results = vector_store.search_concepts(query_embedding, top_k=top_k)
            if not vec_results:
                return []
            
            # 2. Re-hydrate from Neo4j to get the latest graph properties/relationships if needed
            # For now, we fetch the full nodes from Neo4j based on IDs returned by vector store
            concept_ids = [r["id"] for r in vec_results]
            query = "MATCH (n:Concept) WHERE n.id IN $ids RETURN n"
            async with self.session() as session:
                result = await session.run(query, ids=concept_ids)
                data = await result.data()
                # Maintain order from vector store
                nodes_by_id = {record["n"]["id"]: record["n"] for record in data if "n" in record}
                return [nodes_by_id[cid] for cid in concept_ids if cid in nodes_by_id]

        # Fallback for other labels (if they have native Neo4j indexes)
        index_name = f"{label.lower()}_embeddings"
        
        where_clauses = []
        params = {"index": index_name, "query": query_embedding, "k": top_k}
        
        if filters:
            for i, (k, v) in enumerate(filters.items()):
                where_clauses.append(f"node.{k} = $p{i}")
                params[f"p{i}"] = v
        
        where_str = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        query = f"""
        CALL db.index.vector.queryNodes($index, $k, $query)
        YIELD node, score
        {where_str}
        RETURN node, score
        """
        
        async with self.session() as session:
            result = await session.run(query, **params)
            data = await result.data()
            return [record["node"] for record in data if "node" in record]
