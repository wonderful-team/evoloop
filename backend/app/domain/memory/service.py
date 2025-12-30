from app.core.config import settings
from app.infrastructure.database.graph.driver import get_graph_db
from app.logging import logger
from app.domain.codebase.indexing.vectors.openai_embedder import OpenAIEmbedder


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
                logger.warning(f"Failed to create composite constraint: {e}")

            # Vector Index for Concepts
            # Syntax for Neo4j 5.x+
            # IF NOT EXISTS is supported in newer versions.
            try:
                # Check if index exists explicitly if needed, but modern CREATE handles it.
                # using `db.index.vector.createNodeIndex` procedure for compatibility if CREATE fails?
                # We'll use the CREATE syntax.
                await session.run("""
                    CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
                    FOR (c:Concept)
                    ON (c.embedding)
                    OPTIONS {indexConfig: {
                        `vector.dimensions`: 768,
                        `vector.similarity_function`: 'cosine'
                    }}
                """)
                logger.info("Vector Index 'concept_embeddings' ensured.")
            except Exception as e:
                logger.warning(f"Failed to create Vector Index: {e}")

    async def add_user_preference(self, user_id: str, key: str, value: str, description: str = "", project_id: int = None):
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
            await session.run(query, user_id=user_id, key=key, value=value, description=description, pid=pid_val)
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
            key = r['key']
            val = r['value']
            scope_pid = r['pid']
            desc = r['desc']
            final_prefs[key] = f"- {key}: {val} ({desc})" + (" [Global]" if scope_pid == 0 else " [Project]")

        return "\n".join(["**User Preferences:**"] + sorted(final_prefs.values()))

    async def add_concept(self, name: str, description: str, project_id: int, related_files: list[str] = None):
        driver = await get_graph_db()
        pid_val = project_id if project_id is not None else 0
        
        # 1. Generate Embedding
        embedder = OpenAIEmbedder()
        try:
            # Embed content: Name + Description
            embedding = await embedder.embed_query(f"{name}: {description}")
        except Exception as e:
            logger.error(f"Failed to generate embedding for concept {name}: {e}")
            embedding = [] # Fallback, will not be searchable by vector

        query = """
        MERGE (c:Concept {name: $name, project_id: $pid})
        SET c.description = $description, 
            c.updated_at = timestamp(),
            c.embedding = $embedding
        """
        async with driver.session() as session:
            await session.run(query, name=name, pid=pid_val, description=description, embedding=embedding)

            if related_files:
                for file_path in related_files:
                    file_query = """
                    MATCH (c:Concept {name: $name, project_id: $pid})
                    MERGE (f:File {path: $path})
                    MERGE (c)-[:REFERENCES]->(f)
                    """
                    await session.run(file_query, name=name, pid=pid_val, path=file_path)
        
        logger.info(f"Stored Concept (Vectorized): {name} (Project {pid_val})")

    async def search_concepts(self, query_text: str, project_id: int) -> str:
        """
        Semantic Search for Concepts using Vector Index.
        Also traverses to return related file names.
        """
        driver = await get_graph_db()
        
        # 1. Generate Query Embedding
        embedder = OpenAIEmbedder()
        try:
             query_embedding = await embedder.embed_query(query_text)
        except Exception as e:
             logger.error(f"Embedding failed: {e}")
             return f"Error searching concepts: {e}"

        # 2. Vector Search Cypher
        # We query the index, then filter by Project ID
        vector_cypher = """
        CALL db.index.vector.queryNodes('concept_embeddings', $top_k, $embedding)
        YIELD node AS c, score
        WHERE (c.project_id = $pid OR c.project_id = 0)
        
        // Optional: GraphRAG - Fetch connected files
        OPTIONAL MATCH (c)-[:REFERENCES]->(f:File)
        
        RETURN c.name as name, c.description as desc, c.project_id as pid, score, collect(f.path) as files
        """

        async with driver.session() as session:
            # Fetch a bit more than limit to allow for post-filtering if needed, 
            # though WHERE clause inside YIELD usually works efficiently.
            result = await session.run(vector_cypher, embedding=query_embedding, pid=project_id, top_k=settings.MEMORY_SEARCH_LIMIT)
            records = await result.data()

        if not records:
            return "No relevant concepts found."

        lines = []
        for r in records:
            scope = "[Global]" if r['pid'] == 0 else ""
            files_str = ""
            if r['files']:
                 # Just show basenames for brevity
                 basenames = [f.split('/')[-1] for f in r['files']]
                 files_str = f"\n  Related Files: {', '.join(basenames)}"
            
            lines.append(f"- **{r['name']}** {scope} (Score: {r['score']:.2f}): {r['desc']}{files_str}")
            
        return "\n".join(lines)


    async def search_concepts_data(self, query_text: str, project_id: int) -> list[dict]:
        """
        Raw data version of search (for internal use).
        """
        driver = await get_graph_db()
        embedder = OpenAIEmbedder()
        query_embedding = await embedder.embed_query(query_text)
        
        vector_cypher = """
        CALL db.index.vector.queryNodes('concept_embeddings', $top_k, $embedding)
        YIELD node AS c, score
        WHERE (c.project_id = $pid OR c.project_id = 0)
        RETURN c.name as name, c.description as description, c.project_id as project_id
        """
        async with driver.session() as session:
            result = await session.run(vector_cypher, embedding=query_embedding, pid=project_id, top_k=settings.MEMORY_SEARCH_LIMIT)
            records = await result.data()
        return records


memory_service = MemoryService()
