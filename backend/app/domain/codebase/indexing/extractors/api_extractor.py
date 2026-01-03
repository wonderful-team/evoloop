
import re
import logging
from typing import List, Dict
from dataclasses import dataclass

from app.utils.file import read_file_content

logger = logging.getLogger(__name__)

@dataclass
class APIEndpoint:
    method: str
    path: str
    handler_name: str
    file_path: str
    line_number: int

class APIExtractor:
    """
    Extracts API Definitions from code files.
    Currently supports Python (FastAPI/Flask) via Regex heuristics.
    TODO: Upgrade to TreeSitter for robust parsing.
    """
    
    # Matching @router.get("/users") or @app.post('/items/{id}')
    PYTHON_PATTERN = re.compile(r'@(?:router|app)\.(get|post|put|delete|patch|options|head)\s*\(\s*["\']([^"\']+)["\']')
    
    async def extract(self, file_path: str) -> List[APIEndpoint]:
        endpoints = []
        if not file_path.endswith(".py"):
            return []

        try:
            content, _ = read_file_content(file_path)
            if not content: return []
            
            lines = content.splitlines()
            for i, line in enumerate(lines):
                match = self.PYTHON_PATTERN.search(line)
                if match:
                    method = match.group(1).upper()
                    path = match.group(2)
                    
                    # Find handler name (usually next def)
                    # Simple lookahead
                    handler_name = "unknown"
                    for j in range(i + 1, min(i + 5, len(lines))):
                        def_match = re.search(r'def\s+([a-zA-Z0-9_]+)', lines[j])
                        if def_match:
                            handler_name = def_match.group(1)
                            break
                    
                    endpoints.append(APIEndpoint(
                        method=method,
                        path=path,
                        handler_name=handler_name,
                        file_path=file_path,
                        line_number=i + 1
                    ))
                    
            return endpoints
        except Exception as e:
            logger.error(f"API Extraction failed for {file_path}: {e}")
            return []

    async def sync_to_graph(self, project_id: int, endpoints: List[APIEndpoint]):
        if not endpoints: return
        
        try:
            from app.infrastructure.database.graph.driver import get_graph_db
            driver = await get_graph_db()
            async with driver.session() as session:
                for ep in endpoints:
                    # Create Endpoint Node and link to Handler Function (if exists)
                    # We might not find the Function node if it wasn't indexed yet or name mismatch.
                    # But we can create the Endpoint node.
                    
                    full_name = f"{ep.method} {ep.path}" # ID
                    await session.run("""
                        MERGE (e:APIEndpoint {full_name: $id, project_id: $pid})
                        SET e.method = $method, e.path = $path, e.handler = $handler, e.file = $file
                        
                        # Try to link to Function Entity
                        WITH e
                        MATCH (fn:CodeEntity {name: $handler, project_id: $pid}) 
                        # This match is weak (name only). Ideally FQN. 
                        # But for now it's better than nothing.
                        MERGE (e)-[:HANDLED_BY]->(fn)
                    """, id=full_name, pid=project_id, method=ep.method, path=ep.path, 
                         handler=ep.handler_name, file=ep.file_path)
                         
        except Exception as e:
            logger.error(f"Graph Sync for API failed: {e}")

api_extractor = APIExtractor()
