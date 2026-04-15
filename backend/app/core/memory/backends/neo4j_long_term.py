import logging
import time

from app.core.config import settings
from app.core.memory.interfaces.long_term import (
    Concept,
    Episode,
    ILongTermMemory,
    SearchResult,
)
from app.infrastructure.database.graph.driver import get_graph_db
from app.infrastructure.embeddings.factory import EmbedderFactory
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)

# In-memory cache for project concepts with TTL
_CONCEPTS_CACHE: dict[int, tuple[list[str], float]] = {}
_CACHE_TTL = 60.0  # 60 seconds


class Neo4jLongTermMemory(ILongTermMemory):
    """Neo4j implementation of long-term memory interface."""

    async def initialize(self) -> None:
        """Initialize Neo4j schema, constraints, and vector indexes."""
        driver = await get_graph_db()
        async with driver.session() as session:
            # User Constraints
            await session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE")
            # Preference Constraints
            await session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Preference) REQUIRE p.key IS UNIQUE")

            # Concept Constraints - Composite Key
            try:
                await session.run(
                    "CREATE CONSTRAINT concept_unique IF NOT EXISTS FOR (c:Concept) REQUIRE (c.name, c.project_id) IS UNIQUE"
                )
            except Exception as e:
                logger.warning(f"Failed to create composite constraint for Concept: {e}")

            # CodeEntity Constraints - Composite Key (Project Scoped)
            try:
                await session.run(
                    "CREATE CONSTRAINT code_entity_unique IF NOT EXISTS FOR (e:CodeEntity) REQUIRE (e.full_name, e.project_id) IS UNIQUE"
                )
            except Exception as e:
                logger.warning(f"Failed to create composite constraint for CodeEntity: {e}")

            # Vector Index for Concepts & Episodes
            target_dim = settings.EMBEDDING_DIMENSIONS

            try:
                # Validate Embedder
                try:
                    embedder = EmbedderFactory.get_embedder()
                    vec = await embedder.embed_query("dim_check")
                    if vec:
                        target_dim = len(vec)
                        logger.info(f"Neo4jLongTermMemory: Verified Embedder Dimension: {target_dim}")
                except Exception as e:
                    logger.warning(
                        f"Neo4jLongTermMemory: Embedder check failed ({e}). Using configured dimension: {target_dim}"
                    )

                # Check existing index dimensions and recreate if mismatch
                for index_name in ["concept_embeddings", "episode_embeddings"]:
                    try:
                        index_check = await session.run(
                            "SHOW INDEXES YIELD name, options WHERE name = $name", name=index_name
                        )
                        record = await index_check.single()

                        if record:
                            options = record.get("options", {})
                            idx_config = options.get("indexConfig", {})
                            current_dim = idx_config.get("vector.dimensions")

                            if current_dim and int(current_dim) != target_dim:
                                logger.warning(
                                    f"Index '{index_name}' dimension mismatch! Index: {current_dim}, Config: {target_dim}. Recreating..."
                                )
                                await session.run(f"DROP INDEX {index_name} IF EXISTS")
                        else:
                            logger.info(f"Neo4jLongTermMemory: Index '{index_name}' not found, will create.")
                    except Exception as e:
                        logger.warning(f"Error checking index '{index_name}': {e}")

                # Create Vector Indexes
                await session.run(
                    f"""
                    CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
                    FOR (c:Concept)
                    ON (c.embedding)
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {target_dim},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                """
                )

                await session.run(
                    f"""
                     CREATE VECTOR INDEX episode_embeddings IF NOT EXISTS
                     FOR (e:Episode)
                     ON (e.embedding)
                     OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {target_dim},
                        `vector.similarity_function`: 'cosine'
                     }}}}
                """
                )
                logger.info("Neo4jLongTermMemory: Vector Indexes initialized.")

            except Exception as e:
                logger.error(f"Failed to initialize Vector Index: {e}")
                raise

            # Episode Constraints
            try:
                await session.run(
                    "CREATE CONSTRAINT episode_unique IF NOT EXISTS FOR (e:Episode) REQUIRE e.id IS UNIQUE"
                )
                await session.run(
                    "CREATE INDEX episode_message_id IF NOT EXISTS FOR (e:Episode) ON (e.source_message_id)"
                )
            except Exception as e:
                logger.warning(f"Failed to create Episode constraint: {e}")

    async def flush(self) -> None:
        """Clear all memory data (for testing)."""
        driver = await get_graph_db()
        async with driver.session() as session:
            await session.run("MATCH (c:Concept) DETACH DELETE c")
            await session.run("MATCH (e:Episode) DETACH DELETE e")
            await session.run("MATCH (p:Preference) DETACH DELETE p")
            await session.run("MATCH (u:User) DETACH DELETE u")

        # Clear cache
        _CONCEPTS_CACHE.clear()
        logger.info("Neo4jLongTermMemory: Flushed all data")

    async def store_concept(self, concept: Concept) -> None:
        """Store a knowledge concept with embedding."""
        driver = await get_graph_db()
        pid_val = concept.project_id if concept.project_id is not None else 0

        # Generate Embedding
        embedder = EmbedderFactory.get_embedder()
        try:
            embedding = await embedder.embed_query(f"{concept.name}: {concept.description}")
        except Exception as e:
            logger.error(f"Failed to generate embedding for concept {concept.name}: {e}")
            embedding = []

        # Store concept
        query = """
        MERGE (c:Concept {name: $name, project_id: $pid})
        SET c.description = $description,
            c.updated_at = timestamp(),
            c.embedding = $embedding
        """
        async with driver.session() as session:
            await session.run(
                query,
                name=concept.name,
                pid=pid_val,
                description=concept.description,
                embedding=embedding,
            )

            if concept.related_files:
                for file_path in concept.related_files:
                    file_query = """
                    MATCH (c:Concept {name: $name, project_id: $pid})
                    MERGE (f:File {path: $path})
                    MERGE (c)-[:REFERENCES]->(f)
                    """
                    await session.run(file_query, name=concept.name, pid=pid_val, path=file_path)

        # Invalidate cache
        _CONCEPTS_CACHE.pop(pid_val, None)
        logger.info(f"Stored Concept (Vectorized): {concept.name} (Project {pid_val})")

    async def search_concepts(
        self, query: str, project_id: int | None = None, min_score: float = 0.7
    ) -> list[SearchResult]:
        """Semantic search for concepts using vector index."""
        driver = await get_graph_db()

        embedder = EmbedderFactory.get_embedder()
        try:
            query_embedding = await embedder.embed_query(query)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return []

        vector_cypher = """
        CALL db.index.vector.queryNodes('concept_embeddings', $top_k, $embedding)
        YIELD node AS c, score
        """
        if project_id is not None:
            vector_cypher += "WHERE (c.project_id = $pid OR c.project_id = 0) "

        vector_cypher += "AND score >= $min_score " if project_id is not None else "WHERE score >= $min_score "

        vector_cypher += """
        OPTIONAL MATCH (c)-[:REFERENCES]->(f:File)
        RETURN c.name as name, c.description as desc, c.project_id as pid, score, collect(f.path) as files
        """

        async with driver.session() as session:
            result = await session.run(
                vector_cypher,
                embedding=query_embedding,
                pid=project_id,
                top_k=settings.MEMORY_SEARCH_LIMIT,
                min_score=min_score,
            )
            records = await result.data()

        return [
            SearchResult(
                name=r["name"],
                description=r["desc"],
                score=r["score"],
                files=r["files"] if r["files"] else [],
            )
            for r in records
        ]

    async def search_concepts_data(self, query: str, project_id: int | None = None) -> list[dict]:
        """Raw data version of search (for internal use)."""
        driver = await get_graph_db()
        embedder = EmbedderFactory.get_embedder()
        query_embedding = await embedder.embed_query(query)

        vector_cypher = """
        CALL db.index.vector.queryNodes('concept_embeddings', $top_k, $embedding)
        YIELD node AS c, score
        """
        if project_id is not None:
            vector_cypher += "WHERE (c.project_id = $pid OR c.project_id = 0) "

        vector_cypher += "RETURN c.name as name, c.description as description, c.project_id as project_id"
        async with driver.session() as session:
            result = await session.run(
                vector_cypher,
                embedding=query_embedding,
                pid=project_id,
                top_k=settings.MEMORY_SEARCH_LIMIT,
            )
            records = await result.data()
        return records

    async def record_episode(self, episode: Episode) -> str | None:
        """Store a completed task execution as an Episode."""
        driver = await get_graph_db()
        pid_val = episode.project_id if episode.project_id else 0

        # Embed the Goal
        if not episode.goal:
            logger.warning("Episode goal is empty or None, skipping episode recording")
            return None

        embedder = EmbedderFactory.get_embedder()
        try:
            embedding = await embedder.embed_query(episode.goal)
        except Exception as e:
            logger.error(f"Failed to embed episode goal: {e}")
            return None

        # Create Episode Node
        episode_id = gen_uuid()

        query = """
        CREATE (e:Episode {
            id: $id,
            goal: $goal,
            result: $result,
            plan: $plan,
            error: $error,
            project_id: $pid,
            timestamp: timestamp(),
            embedding: $embedding,
            source_message_id: $mid
        })
        RETURN e
        """

        async with driver.session() as session:
            await session.run(
                query,
                id=episode_id,
                goal=episode.goal,
                result=episode.result,
                plan=episode.plan_summary,
                error=episode.error_msg,
                pid=pid_val,
                embedding=embedding,
                mid=episode.source_message_id,
            )
            logger.info(f"Stored Episode: {episode_id} (Result: {episode.result})")

        # Link to Concepts (Heuristic)
        link_query = """
        MATCH (e:Episode {id: $id, project_id: $pid})
        MATCH (c:Concept {project_id: $pid})
        WHERE toLower($goal) CONTAINS toLower(c.name) OR toLower($plan) CONTAINS toLower(c.name)
        MERGE (e)-[:RELATED_TO]->(c)
        """

        async with driver.session() as session:
            await session.run(link_query, id=episode_id, pid=pid_val, goal=episode.goal, plan=episode.plan_summary)
            logger.info(f"Linked Episode {episode_id} to relevant Concepts.")

        return episode_id

    async def retrieve_experience(self, goal: str, project_id: int, top_k: int = 3) -> str:
        """Find past episodes similar to the current goal."""
        driver = await get_graph_db()
        embedder = EmbedderFactory.get_embedder()

        try:
            query_embedding = await embedder.embed_query(goal)
        except Exception as e:
            logger.error(f"Failed to embed goal for search: {e}")
            return ""

        query = """
        CALL db.index.vector.queryNodes('episode_embeddings', $top_k, $embedding)
        YIELD node AS e, score
        WHERE (e.project_id = $pid OR e.project_id = 0)
        RETURN e.goal as goal, e.result as result, e.plan as plan, e.error as error, score
        """

        async with driver.session() as session:
            result = await session.run(query, embedding=query_embedding, pid=project_id, top_k=top_k)
            records = await result.data()

        if not records:
            return ""

        # Prepare data for template rendering
        from app.utils import render_template

        episodes = []
        for r in records:
            if r["score"] < 0.75:
                continue
            episodes.append({
                "status": "FAILED" if r["error"] else "SUCCESS",
                "goal": r["goal"],
                "error": r["error"],
                "plan": r["plan"],
                "score": r["score"],
            })

        if not episodes:
            return ""

        return render_template("core/memory/episodes_summary.prompt.j2", episodes=episodes)

    async def link_episode_to_concepts(
        self, episode_id: str, concept_names: list[str], project_id: int
    ) -> None:
        """Explicitly link an Episode to specific Concepts by name."""
        if not concept_names:
            return

        driver = await get_graph_db()
        pid_val = project_id if project_id else 0

        link_query = """
        MATCH (e:Episode {id: $episode_id, project_id: $pid})
        MATCH (c:Concept {name: $concept_name, project_id: $pid})
        MERGE (e)-[:RELATED_TO]->(c)
        """

        async with driver.session() as session:
            for name in concept_names:
                try:
                    await session.run(
                        link_query,
                        episode_id=episode_id,
                        concept_name=name,
                        pid=pid_val,
                    )
                except Exception as e:
                    logger.warning(f"Failed to link Episode to Concept {name}: {e}")

    async def find_episodes_by_concept(
        self, concept_name: str, project_id: int, limit: int = 10
    ) -> list[dict]:
        """Find Episodes linked to a specific Concept via RELATED_TO edge."""
        driver = await get_graph_db()
        pid_val = project_id if project_id else 0

        query = """
        MATCH (c:Concept {name: $name, project_id: $pid})<-[:RELATED_TO]-(e:Episode)
        RETURN e.id as id, e.goal as goal, e.result as result, e.error as error, e.timestamp as timestamp
        ORDER BY e.timestamp DESC
        LIMIT $limit
        """

        try:
            async with driver.session() as session:
                result = await session.run(query, name=concept_name, pid=pid_val, limit=limit)
                records = await result.data()
                return records
        except Exception as e:
            logger.error(f"Failed to find episodes by concept: {e}")
            return []

    async def list_concepts(self, project_id: int, limit: int = 50) -> list[dict]:
        """List all Concepts for a project."""
        driver = await get_graph_db()
        pid_val = project_id if project_id else 0

        query = """
        MATCH (c:Concept {project_id: $pid})
        OPTIONAL MATCH (c)<-[:RELATED_TO]-(e:Episode)
        RETURN c.name as name, c.description as description, count(e) as episode_count
        ORDER BY episode_count DESC, c.name
        LIMIT $limit
        """

        try:
            async with driver.session() as session:
                result = await session.run(query, pid=pid_val, limit=limit)
                records = await result.data()
                return records
        except Exception as e:
            logger.error(f"Failed to list concepts: {e}")
            return []

    async def get_project_concepts(self, project_id: int) -> list[str]:
        """Retrieve all concepts associated with a project."""
        if project_id in _CONCEPTS_CACHE:
            payload, timestamp = _CONCEPTS_CACHE[project_id]
            if time.time() - timestamp < _CACHE_TTL:
                return payload

        driver = await get_graph_db()
        pid_val = project_id if project_id else 0

        query = """
        MATCH (c:Concept {project_id: $pid})
        RETURN c.name as name, c.description as description
        ORDER BY c.name
        """

        async with driver.session() as session:
            result = await session.run(query, pid=pid_val)
            records = await result.data()

        if not records:
            res = []
        else:
            res = [f"{r['name']}: {r['description']}" for r in records]

        # Update cache
        _CONCEPTS_CACHE[project_id] = (res, time.time())
        return res

    async def delete_episodes_by_message_ids(self, message_ids: list[str]) -> int:
        """Delete episodes linked to specific message IDs."""
        if not message_ids:
            return 0

        driver = await get_graph_db()
        query = """
        MATCH (e:Episode)
        WHERE e.source_message_id IN $message_ids
        DETACH DELETE e
        RETURN count(e) as deleted_count
        """

        try:
            async with driver.session() as session:
                result = await session.run(query, message_ids=message_ids)
                record = await result.single()
                count = record["deleted_count"] if record else 0
                if count > 0:
                    logger.info(f"Deleted {count} episodes linked to rolled-back messages.")
                return count
        except Exception as e:
            logger.error(f"Failed to delete episodes by message IDs: {e}")
            return 0

    async def delete_episodes_by_run_ids(self, run_ids: list[str]) -> int:
        """Delete episodes linked to specific run IDs (source_message_id)."""
        # In Neo4j backend, run_id is stored in source_message_id
        return await self.delete_episodes_by_message_ids(run_ids)
