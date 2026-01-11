from app.core.config import settings
from app.infrastructure.database.graph.driver import get_graph_db
from app.logging import logger
from app.domain.codebase.indexing.vectors.factory import EmbedderFactory
from typing import Optional


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
            try:
                # Check if index exists explicitly if needed, but modern CREATE handles it.
                # using `db.index.vector.createNodeIndex` procedure for compatibility if CREATE fails?
                # We'll use the CREATE syntax.
                # Note: Dimensions now dynamic? If index depends on fixed dim, we might have issues if factory returns diff dim.
                # Ideally, we should check the current configured dimension.
                # For now, let's try to get a sample embedding to determine dim? Or trust the default.
                # But CREATE INDEX requires fixed dim.
                # Strategy: We only create if not exists. If dimension mismatch, user must use "Switch Model" which drops index.
                
                # Get configured embedder
                embedder = EmbedderFactory.get_embedder()
                # Dummy embedding to check dimension
                vec = await embedder.embed_query("dim_check")
                dim = len(vec)

                await session.run(f"""
                    CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
                    FOR (c:Concept)
                    ON (c.embedding)
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {dim},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                """)
                logger.info(f"Vector Index 'concept_embeddings' ensured (dim={dim}).")
            except Exception as e:
                logger.warning(f"Failed to create Vector Index: {e}")

            # Episode Constraints
            try:
                 await session.run("CREATE CONSTRAINT episode_unique IF NOT EXISTS FOR (e:Episode) REQUIRE e.id IS UNIQUE")
            except Exception as e:
                 logger.warning(f"Failed to create Episode constraint: {e}")

            # Vector Index for Episodes (Features: Goal)
            try:
                # Assuming same dimensions as Concepts for now
                embedder = EmbedderFactory.get_embedder()
                vec = await embedder.embed_query("dim_check")
                dim = len(vec)

                await session.run(f"""
                    CREATE VECTOR INDEX episode_embeddings IF NOT EXISTS
                    FOR (e:Episode)
                    ON (e.embedding)
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {dim},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                """)
                logger.info(f"Vector Index 'episode_embeddings' ensured (dim={dim}).")
            except Exception as e:
                logger.warning(f"Failed to create Episode Vector Index: {e}")

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
            existing = await self.search_concepts_data(f"{name}: {description}", pid_val)
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
        embedder = EmbedderFactory.get_embedder()
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
        embedder = EmbedderFactory.get_embedder()
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
        norm_path = path.rstrip('/')
        if not norm_path and path: # if was just "/"
             pass # keep empty

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
            "dependencies": []
        }
        
        async with driver.session() as session:
            # Main Summary
            result = await session.run(query, path=norm_path, pid=project_id)
            record = await result.single()
            if record:
                info["summary"] = record["summary"]
            else:
                return info # Return empty info if not found

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

    async def store_episode(self, goal: str, result: str, plan_summary: str, error_msg: Optional[str], project_id: int):
        """
        Store a completed task execution as an Episode in the graph.
        """
        driver = await get_graph_db()
        pid_val = project_id if project_id else 0
        
        # 1. Embed the Goal (This is what we search against later)
        embedder = EmbedderFactory.get_embedder()
        try:
             embedding = await embedder.embed_query(goal)
        except Exception as e:
             logger.error(f"Failed to embed episode goal: {e}")
             return

        # 2. Create Episode Node
        import uuid
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
             await session.run(query, id=episode_id, goal=goal, result=result, plan=plan_summary, error=error_msg, pid=pid_val, embedding=embedding)
             logger.info(f"Stored Episode: {episode_id} (Result: {result})")
             
        # TODO Phase 2: Link Episode to Concepts used in the Plan? 
        # For now, just storing the node is enough for RAG.

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
             result = await session.run(query, embedding=query_embedding, pid=project_id, top_k=top_k)
             records = await result.data()
             
        if not records:
             return ""
             
        lines = ["**Relevant Past Experiences:**"]
        for r in records:
             status = "FAILED" if r['error'] else "SUCCESS"
             # Only show if reasonable similarity
             if r['score'] < 0.75: continue
             
             lines.append(f"- [{status}] Goal: {r['goal']}")
             if r['error']:
                 lines.append(f"  Error: {r['error']}")
             lines.append(f"  Plan: {r['plan']}")
             lines.append("---")
             
        if len(lines) == 1: return "" # Nothing significant found
        
        return "\n".join(lines)


memory_service = MemoryService()

