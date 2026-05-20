import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.domain.codebase.retrieval.graph_service import GraphService
from app.infrastructure.database.graph.driver import GraphManager
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ServiceVerify")

async def test_graph_service():
    logger.info("--- Testing GraphService Integration ---")
    settings.EMBEDDED_MODE = True
    service = GraphService()
    
    # 1. Setup mock data in FileGraph
    driver = GraphManager.get_driver()
    await driver.upsert_node("File", "path", {"path": "main.py", "project_id": 1})
    await driver.upsert_node("CodeEntity", "full_name", {
        "full_name": "app.main.run",
        "name": "run",
        "type": "function",
        "project_id": 1
    })
    await driver.link_nodes(
        "File", {"path": "main.py"},
        "CodeEntity", {"full_name": "app.main.run"},
        "CONTAINS"
    )
    
    # 2. Test find_symbol_definition
    results = await service.find_symbol_definition("run", 1)
    logger.info(f"Symbol Results: {results}")
    assert len(results) >= 1
    assert results[0]["file_path"] == "main.py"
    
    # 3. Test get_symbol_usages
    # Link Entity -> Entity
    await driver.upsert_node("CodeEntity", "full_name", {
        "full_name": "app.utils.log",
        "name": "log",
        "type": "function",
        "project_id": 1
    })
    await driver.link_nodes(
        "CodeEntity", {"full_name": "app.main.run"},
        "CodeEntity", {"full_name": "app.utils.log"},
        "RELATION",
        rel_props={"type": "calls"}
    )
    
    usages = await service.get_call_hierarchy("log", 1)
    logger.info(f"Usages: {usages}")
    assert usages["incoming"] >= 1
    
    logger.info("GraphService integration PASSED")

if __name__ == "__main__":
    asyncio.run(test_graph_service())
