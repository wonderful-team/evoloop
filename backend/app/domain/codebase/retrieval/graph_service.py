from typing import List, Dict, Any, Optional
from app.infrastructure.database.graph.driver import get_graph_db
from app.logging import logger

class GraphRetrievalService:
    """
    Retrieves Code Structure and Relations from Neo4j.
    Enables 'Find Usages', 'Call Hierarchy', and 'Dependency Analysis'.
    """

    async def find_symbol_definition(self, symbol_name: str, project_id: int) -> List[Dict[str, Any]]:
        """
        Find a symbol definition using Graph.
        """
        driver = await get_graph_db()
        query = """
        MATCH (e:CodeEntity {name: $name, project_id: $pid})
        MATCH (f:File)-[:CONTAINS]->(e)
        RETURN e.full_name as full_name, e.type as type, f.path as file_path, e.score as score
        LIMIT 10
        """
        async with driver.session() as session:
            result = await session.run(query, name=symbol_name, pid=project_id)
            records = await result.data()
            return records

    async def find_usages(self, symbol_name: str, project_id: int) -> List[Dict[str, Any]]:
        """
        Find who uses (calls/references) this symbol.
        Replaces 'grep' for structural usage finding.
        """
        driver = await get_graph_db()
        query = """
        MATCH (target:CodeEntity {name: $name, project_id: $pid})
        MATCH (source:CodeEntity)-[r]->(target)
        MATCH (f:File)-[:CONTAINS]->(source)
        RETURN source.full_name as source, r.type as relation, f.path as file_path, target.full_name as target
        LIMIT 50
        """
        async with driver.session() as session:
            result = await session.run(query, name=symbol_name, pid=project_id)
            records = await result.data()
            return records

    async def get_call_hierarchy(self, symbol_name: str, project_id: int, depth: int = 2) -> Dict[str, Any]:
        """
        Get recursive call hierarchy (Who calls me, who do I call).
        """
        driver = await get_graph_db()
        
        # Incoming (Who calls me)
        incoming_query = f"""
        MATCH (target:CodeEntity {{name: $name, project_id: $pid}})
        MATCH path = (source)-[:RELATION*1..{depth}]->(target)
        RETURN path
        LIMIT 20
        """
        
        # Outgoing (Who do I call)
        outgoing_query = f"""
        MATCH (source:CodeEntity {{name: $name, project_id: $pid}})
        MATCH path = (source)-[:RELATION*1..{depth}]->(target)
        RETURN path
        LIMIT 20
        """
        
        async with driver.session() as session:
            # For visualization, we might return paths. 
            # For simplistic text output, we just count or list unique nodes.
            
            in_res = await session.run(incoming_query, name=symbol_name, pid=project_id)
            in_paths = await in_res.data()
            
            out_res = await session.run(outgoing_query, name=symbol_name, pid=project_id)
            out_paths = await out_res.data()
            
            return {
                "incoming": len(in_paths),
                "outgoing": len(out_paths),
                "details": "Graph paths fetched (summarized for now)" 
            }

graph_retrieval_service = GraphRetrievalService()
