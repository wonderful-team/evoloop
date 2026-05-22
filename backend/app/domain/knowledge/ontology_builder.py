import logging

from app.infrastructure.database.graph.driver import get_graph_db

logger = logging.getLogger(__name__)


class OntologyBuilder:
    """
    Infers High-Level Semantic Relationships (Ontology) from Low-Level Code Graph.
    Transforms 'Call Graph' into 'Architecture Graph'.
    """

    async def infer_relationships(self, project_id: int):
        """
        Main entry point to infer relationships.
        Strategies:
        1. Dependency Inference (Directory Level)
        2. Inheritance Inference (Concept Level)
        """
        await self._infer_directory_dependencies(project_id)
        # await self._infer_concept_inheritance(project_id) # V2

    async def _infer_directory_dependencies(self, project_id: int):
        """
        If many files in Dir A call files in Dir B, then Dir A DEPENDS_ON Dir B.
        """
        driver = await get_graph_db()

        try:
            # Cypher Logic:
            # Match (d1:Directory)-[*]->(f1:File)-[r:RELATION]->(f2:File)<-[*]-(d2:Directory)
            # Where r.type IN ['calls', 'imports']
            # Count relations. If > Threshold, Create (d1)-[:DEPENDS_ON]->(d2)

            # Note: This query is expensive (Cartesian if not careful).
            # Optimized approach: Traverse relations first, then aggregate to dirs.

            optimized_query = """
            MATCH (e1:CodeEntity {project_id: $pid})-[r:RELATION]->(e2:CodeEntity {project_id: $pid})
            WHERE e1.pg_id IS NOT NULL AND e2.pg_id IS NOT NULL // Ensure they are real

            // Find parent files
            MATCH (f1:File)-[:CONTAINS]->(e1)
            MATCH (f2:File)-[:CONTAINS]->(e2)
            WHERE f1 <> f2

            // Aggregate by Directories (Simplistic: Top level folder)
            // We need 'Directory' nodes to exist first (Phase 7 ensures this).
            // Finding specific Directory node from File path requires string parsing in Cypher or Link.
            // Assuming we populated (Dir)-[:CONTAINS]->(File) in Phase 7 via `summarize_directory`
            // Wait, Phase 7 did (Parent)-[:CONTAINS]->(ChildDir), but didn't explicitly link Dir->File in Graph
            // other than implicit path logic.
            // Let's rely on string parsing for V1.

            RETURN f1.path as src_path, f2.path as tgt_path
            """

            # We will do aggregation in Python to determine Directory nodes involved.
            records = await driver.execute_query(optimized_query, pid=project_id)

            # Map: (src_dir, tgt_dir) -> count
            dependency_map = {}

            for r in records:
                src_p = r["src_path"]
                tgt_p = r["tgt_path"]

                # Simple Heuristic: First level directory is the Module.
                src_dir = self._get_module_dir(src_p)
                tgt_dir = self._get_module_dir(tgt_p)

                if src_dir and tgt_dir and src_dir != tgt_dir:
                    key = (src_dir, tgt_dir)
                    dependency_map[key] = dependency_map.get(key, 0) + 1

            # Write back significant dependencies
            for (src, tgt), count in dependency_map.items():
                if count >= 3:
                    # Link Directory Nodes via high-level API
                    await driver.link_nodes(
                        "Directory", {"path": src, "project_id": project_id},
                        "Directory", {"path": tgt, "project_id": project_id},
                        "DEPENDS_ON",
                        rel_props={"weight": count}
                    )
                    logger.info(
                        f"Inferred Architecture: {src} DEPENDS_ON {tgt} (Weight: {count})"
                    )
        except NotImplementedError:
            logger.debug("Ontology inference requires graph features (disabled in embedded mode).")

    def _get_module_dir(self, file_path: str) -> str:
        # Returns parent dir.
        if "/" not in file_path:
            return ""
        return file_path.rsplit("/", 1)[0]


# Global
ontology_builder = OntologyBuilder()
