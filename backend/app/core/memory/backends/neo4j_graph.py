"""Neo4j implementation of graph navigator for structural insights."""

import logging
from typing import Any

from app.core.memory.interfaces.graph import IGraphNavigator
from app.infrastructure.database.graph.driver import get_graph_db

logger = logging.getLogger(__name__)


class Neo4jGraphNavigator(IGraphNavigator):
    """Neo4j implementation for graph traversal and architectural insights."""

    async def initialize(self) -> None:
        """Initialize graph constraints (shared with long-term memory)."""
        # Graph constraints are already created by long-term memory
        logger.info("Neo4jGraphNavigator: Initialized")

    async def flush(self) -> None:
        """Clear graph data (directories, code entities)."""
        driver = await get_graph_db()
        async with driver.session() as session:
            await session.run("MATCH (d:Directory) DETACH DELETE d")
            await session.run("MATCH(e:CodeEntity) DETACH DELETE e")
            await session.run("MATCH (f:File) DETACH DELETE f")
        logger.info("Neo4jGraphNavigator: Flushed graph data")

    async def get_node_details(self, node_type: str, filters: dict[str, Any]) -> dict:
        """Retrieve detailed information about a specific node."""
        driver = await get_graph_db()

        # Build filter string
        filter_clauses = [f"n.{k} = ${k}" for k in filters.keys()]
        where_clause = " AND ".join(filter_clauses) if filter_clauses else "true"

        query = f"""
        MATCH (n:{node_type})
        WHERE {where_clause}
        RETURN n
        LIMIT 1
        """

        async with driver.session() as session:
            result = await session.run(query, **filters)
            record = await result.single()

            if not record:
                return {}

            node = record["n"]
            return dict(node.items())

    async def traverse(
        self, start_node_id: str, relation_type: str, max_depth: int = 2
    ) -> list[dict[str, Any]]:
        """Traverse the graph following specific relationships."""
        driver = await get_graph_db()

        query = f"""
        MATCH path = (start)-[:{relation_type}*1..{max_depth}]->(target)
        WHERE id(start) = $start_id
        RETURN collect(DISTINCT target) as nodes
        """

        async with driver.session() as session:
            result = await session.run(query, start_id=int(start_node_id))
            record = await result.single()

            if not record or not record["nodes"]:
                return []

            return [dict(node.items()) for node in record["nodes"]]

    async def get_directory_info(self, project_id: int, path: str) -> dict:
        """Retrieve architectural summary for a directory."""
        driver = await get_graph_db()

        # Normalize path
        norm_path = path.rstrip("/")
        if not norm_path and path:
            pass  # keep empty

        query = """
        MATCH (d:Directory {path: $path, project_id: $pid})
        RETURN d.description as summary
        """

        sub_query = """
        MATCH (d:Directory {path: $path, project_id: $pid})-[:CONTAINS]->(sub:Directory)
        RETURN sub.path as path, sub.description as summary
        """

        dep_query = """
        MATCH (d:Directory {path: $path, project_id: $pid})-[r:DEPENDS_ON]->(target:Directory)
        RETURN target.path as target, r.weight as weight
        """

        info = {
            "path": norm_path,
            "summary": "No summary available (Directory not indexed or not found).",
            "sub_modules": [],
            "dependencies": [],
        }

        async with driver.session() as session:
            # Main Summary
            result = await session.run(query, path=norm_path, pid=project_id)
            record = await result.single()
            if record:
                info["summary"] = record["summary"]
            else:
                return info

            # Sub-modules
            result = await session.run(sub_query, path=norm_path, pid=project_id)
            subs = await result.data()
            info["sub_modules"] = [
                {"name": s["path"].split("/")[-1], "summary": s["summary"]} for s in subs
            ]

            # Dependencies
            result = await session.run(dep_query, path=norm_path, pid=project_id)
            deps = await result.data()
            info["dependencies"] = [{"target": d["target"], "weight": d["weight"]} for d in deps]

        return info

    async def search(self, query: str, limit: int = 5) -> str:
        """Search the graph for nodes matching the query."""
        driver = await get_graph_db()
        
        # Simple keyword matching across Concept nodes (or other types if needed)
        # We use a case-insensitive CONTAINS search on name or description
        cypher_query = """
        MATCH (n:Concept)
        WHERE toLower(n.name) CONTAINS toLower($query) OR toLower(n.description) CONTAINS toLower($query)
        RETURN n.name as name, n.description as description
        LIMIT $limit
        """
        
        results = []
        async with driver.session() as session:
            result = await session.run(cypher_query, {"query": query, "limit": limit})
            records = await result.data()
            
            for record in records:
                results.append(f"- **{record['name']}**: {record['description']}")
                
        if not results:
            return ""
            
        return "\n".join(results)
