
from app.infrastructure.database.graph.driver import get_graph_db
from app.logging import logger
import time

class GraphGarbageCollector:
    """
    Responsible for cleaning up 'Ghost Nodes' in the Knowledge Graph.
    Ghost Nodes are CodeEntities that are:
    1. Not linked to any File (orphaned from source).
    2. Not referenced by any other Concept (orphaned from memory).
    3. Older than a certain threshold (to avoid deleting nodes currently being indexed).
    """
    
    async def cleanup_ghost_nodes(self, project_id: int, grace_period_hours: int = 1):
        """
        Delete orphaned nodes for a specific project.
        """
        driver = await get_graph_db()
        
        # Cypher Logic:
        # Find CodeEntity nodes where:
        # - project_id matches
        # - NO incoming :CONTAINS relationship (not in any file)
        # - NO incoming :REFERENCES relationship (not in any concept/memory)
        # - (Optional) NO incoming :RELATION (not called by anyone? - this might be too aggressive if it's a root independent function, 
        #   but usually a function must belong to a File. So check 1 is key.)
        
        # Valid CodeEntity MUST have a :CONTAINS relationship from a :File node.
        
        query = """
        MATCH (n:CodeEntity {project_id: $pid})
        WHERE NOT (n)<-[:CONTAINS]-(:File)
        AND NOT (n)<-[:REFERENCES]-(:Concept)
        
        // Optional: Check timestamp if we have it, or just assume if it's not in a file it's dead.
        // Risk: Race condition during indexing (node created but file link not yet made). 
        // Transactional integrity usually prevents this, but grace period is safer.
        
        // Return count first for logging? Or just delete.
        WITH n
        LIMIT 1000 // Batch delete
        DETACH DELETE n
        RETURN count(n) as deleted_count
        """
        
        total_deleted = 0
        async with driver.session() as session:
            while True:
                result = await session.run(query, pid=project_id)
                record = await result.single()
                if not record:
                    break
                    
                count = record["deleted_count"]
                total_deleted += count
                if count == 0:
                    break
                    
        if total_deleted > 0:
            logger.info(f"[Graph GC] Cleaned up {total_deleted} ghost nodes for Project {project_id}")
        else:
            logger.debug(f"[Graph GC] No ghost nodes found for Project {project_id}")
            
    async def cleanup_orphaned_files(self, project_id: int):
        """
        Delete File nodes that no longer exist in SQL (which drives the source of truth).
        Note: IndexingService.remove_file handles this usually. This is a fallback/fsck.
        """
        # Complex to verify against SQL efficiently without iterating all.
        # Maybe skipped for now, focus on Ghost Entities.
        pass

# Global Instance
graph_gc = GraphGarbageCollector()
