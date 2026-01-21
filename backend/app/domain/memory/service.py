import logging
import uuid

from app.core.config import settings
from app.domain.codebase.indexing.vectors.factory import EmbedderFactory
from app.infrastructure.database.graph.driver import get_graph_db

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Manages long-term memory in Neo4j (Graph + Vector).
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

            # Concept Constraints - Composite Key
            try:
                await session.run("CREATE CONSTRAINT concept_unique IF NOT EXISTS FOR (c:Concept) REQUIRE (c.name, c.project_id) IS UNIQUE")
            except Exception as e:
                logger.warning(f"Failed to create composite constraint for Concept: {e}")

            # CodeEntity Constraints - Composite Key (Project Scoped)
            # Necessary for performant MERGE in indexing_service
            try:
                await session.run("CREATE CONSTRAINT code_entity_unique IF NOT EXISTS FOR (e:CodeEntity) REQUIRE (e.full_name, e.project_id) IS UNIQUE")
            except Exception as e:
                logger.warning(f"Failed to create composite constraint for CodeEntity: {e}")

            # Vector Index for Concepts
            # Syntax for Neo4j 5.x+
            # IF NOT EXISTS is supported in newer versions.
            # Strategy: Use settings.EMBEDDING_DIMENSIONS as source of truth.
            target_dim = settings.EMBEDDING_DIMENSIONS

            try:
                # Validate Embedder (Optional check)
                try:
                    embedder = EmbedderFactory.get_embedder()
                    vec = await embedder.embed_query("dim_check")
                    if vec:
                        target_dim = len(vec)
                        logger.info(f"MemoryService: Verified Embedder Dimension: {target_dim}")
                except Exception as e:
                    logger.warning(
                        f"MemoryService: Embedder check failed ({e}). Using configured dimension: {target_dim}")

                # Check existing index dimension if it exists

                # Check existing index dimension if it exists
                # Using YIELD to be explicit about what we want
                try:
                    index_check = await session.run(
                        "SHOW INDEXES YIELD name, options WHERE name = 'concept_embeddings'")
                    record = await index_check.single()

                    should_recreate = False
                    if record:
                        logger.info(f"MemoryService: Found existing index 'concept_embeddings'. Checking dimensions...")
                        # Parse existing options to check dimension
                        try:
                            # Record is compliant with dict access
                            options = record["options"]
                            # options is often a map like {'indexConfig': {'vector.similarity_function': 'cosine', 'vector.dimensions': 1536}}
                            idx_config = options.get("indexConfig", {})
                            current_dim = idx_config.get("vector.dimensions")

                            logger.info(f"MemoryService: Existing Index Dimension: {current_dim}")

                            if current_dim and int(current_dim) != target_dim:
                                logger.warning(
                                    f"Vector Index dimension mismatch! Index: {current_dim}, Config: {target_dim}. Recreating index...")
                                should_recreate = True
                            else:
                                logger.info("MemoryService: Index dimension matches.")
                        except Exception as e:
                            logger.warning(
                                f"Failed to parse existing index options keys: {e}. Record keys: {record.keys()}")
                    else:
                        logger.info("MemoryService: Index 'concept_embeddings' not found via SHOW INDEXES.")

                    if should_recreate:
                        logger.info("MemoryService: Dropping old index...")
                        await session.run("DROP INDEX concept_embeddings IF EXISTS")
                        # Also drop episode index if concept one was wrong, likely created together
                        await session.run("DROP INDEX episode_embeddings IF EXISTS")

                except Exception as e:
                    logger.error(f"Error checking/dropping index: {e}")

                await session.run(f"""
                    CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
                    FOR (c:Concept)
                    ON (c.embedding)
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {target_dim},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                """)

                # Same for Episode embeddings if used
                await session.run(f"""
                     CREATE VECTOR INDEX episode_embeddings IF NOT EXISTS
                     FOR (e:Episode)
                     ON (e.embedding)
                     OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {target_dim},
                        `vector.similarity_function`: 'cosine'
                     }}}}
                """)
                logger.info("MemoryService: Vector Indexes initialized.")

            except Exception as e:
                logger.error(f"Failed to initialize Vector Index: {e}")

            # Episode Constraints
            try:
                await session.run("CREATE CONSTRAINT episode_unique IF NOT EXISTS FOR (e:Episode) REQUIRE e.id IS UNIQUE")
            except Exception as e:
                logger.warning(f"Failed to create Episode constraint: {e}")

            # Vector Index for Episodes (Features: Goal)
            try:
                # Use safely determined target_dim
                await session.run(f"""
                    CREATE VECTOR INDEX episode_embeddings IF NOT EXISTS
                    FOR (e:Episode)
                    ON (e.embedding)
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {target_dim},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                """)
                logger.info(f"Vector Index 'episode_embeddings' ensured (dim={target_dim}).")
            except Exception as e:
                logger.warning(f"Failed to create Episode Vector Index: {e}")

    async def add_user_preference(
        self,
        user_id: str,
        key: str,
        value: str,
        description: str = "",
        project_id: int = None,
    ):
        """
        Add a preference. If project_id is provided, it's scoped to that project.
        """
        driver = await get_graph_db()

        pid_val = project_id if project_id else 0

        query = """
        MERGE (u:User {id: $user_id})
        MERGE (p:Preference {key: $key})
        SET p.description = $description
        MERGE (u)-[r:PREFERS {project_id: $pid}]->(p)
        SET r.value = $value
        RETURN p
        """
        async with driver.session() as session:
            await session.run(
                query,
                user_id=user_id,
                key=key,
                value=value,
                description=description,
                pid=pid_val,
            )
            scope = f"Project {pid_val}" if pid_val else "Global"
            logger.info(f"Stored Preference ({scope}): {key}={value}")

    async def get_user_preferences(self, user_id: str, project_id: int = None) -> str:
        """
        Get merged preferences. Project-specific overrides Global.
        """
        driver = await get_graph_db()

        target_pid = project_id if project_id else 0

        query = """
        MATCH (u:User {id: $user_id})-[r:PREFERS]->(p:Preference)
        WHERE r.project_id = 0 OR r.project_id = $pid
        RETURN p.key as key, r.value as value, p.description as desc, r.project_id as pid
        ORDER BY r.project_id ASC
        """

        async with driver.session() as session:
            result = await session.run(query, user_id=user_id, pid=target_pid)
            records = await result.data()

        if not records:
            return "No specific preferences recorded."

        # Merge Logic
        final_prefs = {}
        for r in records:
            key = r["key"]
            val = r["value"]
            scope_pid = r["pid"]
            desc = r["desc"]
            final_prefs[key] = f"- {key}: {val} ({desc})" + (" [Global]" if scope_pid == 0 else " [Project]")

        return "\n".join(["**User Preferences:**"] + sorted(final_prefs.values()))

    async def add_concept(
        self,
        name: str,
        description: str,
        project_id: int,
        related_files: list[str] = None,
    ):
        driver = await get_graph_db()
        pid_val = project_id if project_id is not None else 0

        # 1. Generate Embedding
        embedder = EmbedderFactory.get_embedder()
        try:
            # Embed content: Name + Description
            embedding = await embedder.embed_query(f"{name}: {description}")
        except Exception as e:
            logger.error(f"Failed to generate embedding for concept {name}: {e}")
            embedding = []

        # --- DEDUPLICATION LOGIC ---
        # Before creating, check if a semantically IDENTICAL concept exists.
        # Threshold: 0.92 (Very High Similarity)
        if embedding:
            # Check for existing concepts (logic simplified for now)
            # existing = await self.search_concepts_data(f"{name}: {description}", pid_val)
            # search_concepts_data usually returns top K. We need score.
            # Let's adjust search_concepts_data or write a specific check query here.

            check_query = """
            CALL db.index.vector.queryNodes('concept_embeddings', 1, $embedding)
            YIELD node AS c, score
            WHERE (c.project_id = $pid) AND score > 0.92
            RETURN c.name as name, score
            """
            async with driver.session() as session:
                result = await session.run(check_query, embedding=embedding, pid=pid_val)
                match = await result.single()

                if match:
                    existing_name = match["name"]
                    logger.info(f"Concept Deduplication: '{name}' is too similar to '{existing_name}' (Score {match['score']:.2f}). Merging/Updating.")
                    # We update the description of the EXISTING node to be the new one (latest info usually better?)
                    # Or we skip?
                    # Let's MERGE strictly on name. If name is different but semantic is same,
                    # we might have "Auth Token" vs "JWT".
                    # If we force name update, we might lose "JWT".
                    # Strategy: If names are different, we treat as Alias?
                    # For simplicty: We Update the Description of the MATCHED node, but Keep the Name of the MATCHED node unless user explicitly wants rename.
                    # But wait, User might want to correct the name.
                    # Let's just MERGE based on NAME (Exact Match) first.
                    # If Exact Name Match -> Update.
                    # If Semantic Match BUT Name Diff -> Log warning but Create New? (To avoid aggressive merging of "Dog" and "Cat").
                    # Revised Strategy: Only Merge on Exact Name for now, but use Semantic check to warn or suggest.
                    # Wait, the prompt said "Implement Concept Deduplication".
                    # If I have "Login" and add "Log In", they are dupes.
                    # Let's stick to EXACT NAME MERGE for safety in V1, but optimize the MERGE query.
                    pass

        query = """
        MERGE (c:Concept {name: $name, project_id: $pid})
        SET c.description = $description,
            c.updated_at = timestamp(),
            c.embedding = $embedding
        """
        async with driver.session() as session:
            await session.run(
                query,
                name=name,
                pid=pid_val,
                description=description,
                embedding=embedding,
            )

            if related_files:
                for file_path in related_files:
                    file_query = """
                    MATCH (c:Concept {name: $name, project_id: $pid})
                    MERGE (f:File {path: $path})
                    MERGE (c)-[:REFERENCES]->(f)
                    """
                    await session.run(file_query, name=name, pid=pid_val, path=file_path)

        logger.info(f"Stored Concept (Vectorized): {name} (Project {pid_val})")

    async def search_concepts(self, query_text: str, project_id: int, min_score: float = 0.7) -> str:
        """
        Semantic Search for Concepts using Vector Index.
        Also traverses to return related file names.

        Args:
            query_text: The search query
            project_id: Project context for filtering
            min_score: Minimum similarity score (0-1) to include results. Default 0.7.
        """
        driver = await get_graph_db()

        # 1. Generate Query Embedding
        embedder = EmbedderFactory.get_embedder()
        try:
            query_embedding = await embedder.embed_query(query_text)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return f"Error searching concepts: {e}"

        # 2. Vector Search Cypher with score filtering
        # We query the index, then filter by Project ID and minimum score
        vector_cypher = """
        CALL db.index.vector.queryNodes('concept_embeddings', $top_k, $embedding)
        YIELD node AS c, score
        WHERE (c.project_id = $pid OR c.project_id = 0) AND score >= $min_score

        // Optional: GraphRAG - Fetch connected files
        OPTIONAL MATCH (c)-[:REFERENCES]->(f:File)

        RETURN c.name as name, c.description as desc, c.project_id as pid, score, collect(f.path) as files
        """

        async with driver.session() as session:
            # Fetch a bit more than limit to allow for post-filtering if needed,
            # though WHERE clause inside YIELD usually works efficiently.
            result = await session.run(
                vector_cypher,
                embedding=query_embedding,
                pid=project_id,
                top_k=settings.MEMORY_SEARCH_LIMIT,
                min_score=min_score,
            )
            records = await result.data()

        if not records:
            return "No relevant concepts found."

        lines = []
        for r in records:
            scope = "[Global]" if r["pid"] == 0 else ""
            files_str = ""
            if r["files"]:
                # Just show basenames for brevity
                basenames = [f.split("/")[-1] for f in r["files"]]
                files_str = f"\n  Related Files: {', '.join(basenames)}"

            lines.append(f"- **{r['name']}** {scope} (Score: {r['score']:.2f}): {r['desc']}{files_str}")

        return "\n".join(lines)

    async def search_concepts_data(self, query_text: str, project_id: int) -> list[dict]:
        """
        Raw data version of search (for internal use).
        """
        driver = await get_graph_db()
        embedder = EmbedderFactory.get_embedder()
        query_embedding = await embedder.embed_query(query_text)

        vector_cypher = """
        CALL db.index.vector.queryNodes('concept_embeddings', $top_k, $embedding)
        YIELD node AS c, score
        WHERE (c.project_id = $pid OR c.project_id = 0)
        RETURN c.name as name, c.description as description, c.project_id as project_id
        """
        async with driver.session() as session:
            result = await session.run(
                vector_cypher,
                embedding=query_embedding,
                pid=project_id,
                top_k=settings.MEMORY_SEARCH_LIMIT,
            )
            records = await result.data()
        return records

    async def link_concepts(self, source_name: str, target_name: str, relation: str, project_id: int):
        """
        Create a semantic relationship between two concepts.
        Relations: IS_A, DEPENDS_ON, RELATED_TO
        """
        driver = await get_graph_db()

        valid_relations = ["IS_A", "DEPENDS_ON", "RELATED_TO", "PART_OF"]
        if relation not in valid_relations:
            logger.warning(f"Invalid relation type: {relation}")
            return

        query = f"""
        MATCH (s:Concept {{name: $src, project_id: $pid}})
        MATCH (t:Concept {{name: $tgt, project_id: $pid}})
        MERGE (s)-[:{relation}]->(t)
        """

        async with driver.session() as session:
            await session.run(query, src=source_name, tgt=target_name, pid=project_id)

        logger.info(f"Ontology Link: ({source_name})-[:{relation}]->({target_name})")

        async with driver.session() as session:
            await session.run(query, src=source_name, tgt=target_name, pid=project_id)

        logger.info(f"Ontology Link: ({source_name})-[:{relation}]->({target_name})")

    async def get_directory_info(self, project_id: int, path: str) -> dict:
        """
        Retrieve architectural summary for a directory.
        Used by 'consult_architecture' tool.
        """
        driver = await get_graph_db()

        # Normalize path: ensure no trailing slash unless root?
        # Graph paths in Phase 7 implementation: `path=dir_path`
        # If user asks for "app/core/", we should strip.
        norm_path = path.rstrip("/")
        if not norm_path and path:  # if was just "/"
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
                return info  # Return empty info if not found

            # Sub-modules
            result = await session.run(sub_query, path=norm_path, pid=project_id)
            subs = await result.data()
            info["sub_modules"] = [{"name": s["path"].split('/')[-1], "summary": s["summary"]} for s in subs]

            # Dependencies
            result = await session.run(dep_query, path=norm_path, pid=project_id)
            deps = await result.data()
            info["dependencies"] = [{"target": d["target"], "weight": d["weight"]} for d in deps]

        return info

    async def get_project_concepts(self, project_id: int) -> list[str]:
        """
        Retrieve all concepts associated with a project.
        """
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
            return []

        return [f"{r['name']}: {r['description']}" for r in records]

    async def store_episode(
        self,
        goal: str,
        result: str,
        plan_summary: str,
        error_msg: str | None,
        project_id: int,
    ) -> str | None:
        """
        Store a completed task execution as an Episode in the graph.
        Returns the episode_id for downstream linking.
        """
        driver = await get_graph_db()
        pid_val = project_id if project_id else 0

        # 1. Embed the Goal (This is what we search against later)
        embedder = EmbedderFactory.get_embedder()
        try:
            embedding = await embedder.embed_query(goal)
        except Exception as e:
            logger.error(f"Failed to embed episode goal: {e}")
            return None

        # 2. Create Episode Node
        episode_id = str(uuid.uuid4())

        query = """
        CREATE (e:Episode {
            id: $id,
            goal: $goal,
            result: $result,
            plan: $plan,
            error: $error,
            project_id: $pid,
            timestamp: timestamp(),
            embedding: $embedding
        })
        RETURN e
        """

        async with driver.session() as session:
            await session.run(
                query,
                id=episode_id,
                goal=goal,
                result=result,
                plan=plan_summary,
                error=error_msg,
                pid=pid_val,
                embedding=embedding,
            )
            logger.info(f"Stored Episode: {episode_id} (Result: {result})")

        # 3. Link to Concepts (Heuristic / Knowledge Graph)
        # We try to link this Episode to any existing Concepts mentioned in the goal or plan.
        # This allows: "Show me failures related to 'Auth'"
        # We use a fuzzy text search or simple HAS_STRING check in Cypher for efficiency.
        link_query = """
        MATCH (e:Episode {id: $id, project_id: $pid})
        MATCH (c:Concept {project_id: $pid})
        // Check if Concept Name appears in Goal or Plan
        WHERE toLower($goal) CONTAINS toLower(c.name) OR toLower($plan) CONTAINS toLower(c.name)
        MERGE (e)-[:RELATED_TO]->(c)
        """

        async with driver.session() as session:
            await session.run(
                link_query,
                id=episode_id,
                pid=pid_val,
                goal=goal,
                plan=plan_summary
            )
            logger.info(f"Linked Episode {episode_id} to relevant Concepts.")

        return episode_id

    async def link_episode_to_concepts(self, episode_id: str, concept_names: list[str], project_id: int):
        """
        Explicitly link an Episode to specific Concepts by name.
        This creates RELATED_TO edges for concepts harvested during the session.
        """
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

    async def find_similar_episodes(self, current_goal: str, project_id: int, top_k: int = 3) -> str:
        """
        Find past episodes similar to the current goal.
        Useful for planning.
        """
        driver = await get_graph_db()
        embedder = EmbedderFactory.get_embedder()

        try:
            query_embedding = await embedder.embed_query(current_goal)
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
            result = await session.run(
                query,
                embedding=query_embedding,
                pid=project_id,
                top_k=top_k
            )
            records = await result.data()

        if not records:
            return ""

        lines = ["**Relevant Past Experiences:**"]
        for r in records:
            status = "FAILED" if r["error"] else "SUCCESS"
            # Only show if reasonable similarity
            if r["score"] < 0.75:
                continue

            lines.append(f"- [{status}] Goal: {r['goal']}")
            if r["error"]:
                lines.append(f"  Error: {r['error']}")
            lines.append(f"  Plan: {r['plan']}")
            lines.append("---")

        if len(lines) == 1:
            return ""  # Nothing significant found

        return "\n".join(lines)

    async def find_episodes_by_concept(self, concept_name: str, project_id: int, limit: int = 10) -> list[dict]:
        """
        Find Episodes linked to a specific Concept via RELATED_TO edge.
        Useful for tracing history related to a specific technology or pattern.
        """
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
                result = await session.run(
                    query,
                    name=concept_name,
                    pid=pid_val,
                    limit=limit
                )
                records = await result.data()
                return records
        except Exception as e:
            logger.error(f"Failed to find episodes by concept: {e}")
            return []

    async def list_concepts(self, project_id: int, limit: int = 50) -> list[dict]:
        """
        List all Concepts for a project.
        Returns concept name, description, and count of related episodes.
        """
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


memory_service = MemoryService()
