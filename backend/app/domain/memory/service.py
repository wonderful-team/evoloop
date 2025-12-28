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
            
            # Concept Constraints - Migration to Composite Key
            # 1. Drop old single-property unique constraint if it exists
            # Note: The syntax for dropping constraints varies by Neo4j version.
            try:
                # Syntax for Neo4j 4.x/5.x
                await session.run("DROP CONSTRAINT ON (c:Concept) ASSERT c.name IS UNIQUE")
                logger.info("Dropped legacy Concept name constraint.")
            except Exception:
                # Might not exist or different syntax, ignore
                pass

            # 2. Create new Composite Constraint (Name + ProjectID)
            try:
                # Syntax: CREATE CONSTRAINT [name] FOR (n:Label) REQUIRE (n.prop1, n.prop2) IS UNIQUE
                # We use IF NOT EXISTS to be safe.
                await session.run("CREATE CONSTRAINT concept_unique IF NOT EXISTS FOR (c:Concept) REQUIRE (c.name, c.project_id) IS UNIQUE")
            except Exception as e:
                logger.warning(f"Failed to create composite constraint: {e}")

            # Fulltext Index for Concepts (if supported, else simple lookup)
            try:
                await session.run("CREATE FULLTEXT INDEX concept_search IF NOT EXISTS FOR (c:Concept) ON EACH [c.name, c.description]")
            except Exception:
                logger.warning("Fulltext index creation failed (might already exist or not supported).")

    async def add_user_preference(self, user_id: str, key: str, value: str, description: str = "", project_id: int = None):
        """
        Add a preference. If project_id is provided, it's scoped to that project.
        Otherwise it is a global preference.
        """
        driver = await get_graph_db()
        
        # We store project_id on the relationship PREFERS
        # if project_id is None, we set it to 0 or leave property unset?
        # Cypher: SET r.project_id = $pid
        
        pid_val = project_id if project_id else 0 # Use 0 for global if needed or just handle nulls
        # Let's use 0 for "Global" to make queries simpler (no IS NULL checks mixed with values)
        
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
        # Fetch ALL preferences for user, then filter/merge in app logic or Cypher
        # Cypher approach:
        # Match all PREFERS edges where project_id is 0 OR project_id is current
        
        target_pid = project_id if project_id else 0
        
        query = """
        MATCH (u:User {id: $user_id})-[r:PREFERS]->(p:Preference)
        WHERE r.project_id = 0 OR r.project_id = $pid
        RETURN p.key as key, r.value as value, p.description as desc, r.project_id as pid
        ORDER BY r.project_id ASC
        """
        # Ordering by ASC (0 first, then specific ID) helps us override easily? 
        # Actually we just want a dictionary: map[key] = value.
        # If we process Global (0) first, then Project (ID), the latter overwrites.
        
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
            
            # Since we iterate, later ones overwrite earlier ones?
            # We didn't enforce specific order in query for "same key" collisions across scopes?
            # Actually we typically have one node per Key (unique constraint).
            # But the user might have TWO edges to the SAME key node: one global, one project.
            # So `records` might contain:
            # {key: "test", value: "pytest", pid: 0}
            # {key: "test", value: "jest", pid: 2}
            # We want "jest".
            # So we should sort by pid ASC (0..N). Yes.
            
            final_prefs[key] = f"- {key}: {val} ({desc})" + (" [Global]" if scope_pid == 0 else " [Project]")

        # Sort keys for display
        return "\n".join(["**User Preferences:**"] + sorted(final_prefs.values()))

    async def add_concept(self, name: str, description: str, project_id: int, related_files: list[str] = None):
        driver = await get_graph_db()
        # Ensure project_id is set
        pid_val = project_id if project_id is not None else 0
        
        query = """
        MERGE (c:Concept {name: $name, project_id: $pid})
        SET c.description = $description, c.updated_at = timestamp()
        """
        async with driver.session() as session:
            await session.run(query, name=name, pid=pid_val, description=description)

            if related_files:
                for file_path in related_files:
                    # We assume File nodes already exist from Indexer, but we use MERGE to be safe
                    file_query = """
                    MATCH (c:Concept {name: $name, project_id: $pid})
                    MERGE (f:File {path: $path})
                    MERGE (c)-[:REFERENCES]->(f)
                    """
                    await session.run(file_query, name=name, pid=pid_val, path=file_path)
        logger.info(f"Stored Concept: {name} (Project {pid_val})")

    async def search_concepts(self, query_text: str, project_id: int) -> str:
        driver = await get_graph_db()
        # Search Global (0) and Project (N)
        # Use fulltext index if available, else regex search
        
        fallback_cypher = """
        MATCH (c:Concept)
        WHERE (c.project_id = $pid OR c.project_id = 0) 
          AND (c.name CONTAINS $search_term OR c.description CONTAINS $search_term)
        RETURN c.name as name, c.description as desc, c.project_id as pid
        ORDER BY c.project_id ASC
        LIMIT $limit
        """

        async with driver.session() as session:
            # For simplicity in this fix, we use the fallback logic which supports property filtering easily.
            # Fulltext index with property filter requires Neo4j 4.3+ or trickier query structure.
            result = await session.run(fallback_cypher, search_term=query_text, pid=project_id, limit=settings.MEMORY_SEARCH_LIMIT)
            records = await result.data()

        if not records:
            return "No relevant concepts found."

        lines = []
        for r in records:
            scope = "[Global]" if r['pid'] == 0 else ""
            lines.append(f"- **{r['name']}** {scope}: {r['desc']}")
        return "\n".join(lines)


    async def search_concepts_data(self, query_text: str, project_id: int) -> list[dict]:
        driver = await get_graph_db()
        fallback_cypher = """
        MATCH (c:Concept)
        WHERE (c.project_id = $pid OR c.project_id = 0) 
          AND (c.name CONTAINS $search_term OR c.description CONTAINS $search_term)
        RETURN c.name as name, c.description as description, c.project_id as project_id
        ORDER BY c.project_id ASC
        LIMIT $limit
        """
        async with driver.session() as session:
            result = await session.run(fallback_cypher, search_term=query_text, pid=project_id, limit=settings.MEMORY_SEARCH_LIMIT)
            records = await result.data()
        return records


memory_service = MemoryService()
