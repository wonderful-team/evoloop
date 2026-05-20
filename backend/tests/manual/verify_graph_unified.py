import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.infrastructure.database.graph.driver import GraphManager
from app.infrastructure.database.graph.file_graph import FileGraphDriver
from app.core.memory.backends.graph_backend import GraphMemoryStorage
from app.core.memory.models import MemoryEntry, MemoryType
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GraphVerify")

async def test_driver_parity(driver):
    logger.info(f"--- Testing Driver: {driver.__class__.__name__} ---")
    
    # 1. Upsert Node
    node = await driver.upsert_node("TestNode", "id", {"id": "test_1", "name": "Agnostic Node", "version": 1})
    logger.info(f"Created node: {node}")
    
    # 2. Update Node
    updated = await driver.upsert_node("TestNode", "id", {"id": "test_1", "version": 2})
    logger.info(f"Updated node: {updated}")
    
    # 3. Find Nodes
    found = await driver.find_nodes("TestNode", {"id": "test_1"})
    logger.info(f"Found nodes: {len(found)}")
    assert len(found) == 1
    assert found[0]["version"] == 2
    
    # 4. Link Nodes
    await driver.upsert_node("TargetNode", "id", {"id": "target_1", "name": "Target"})
    linked = await driver.link_nodes(
        "TestNode", {"id": "test_1"},
        "TargetNode", {"id": "target_1"},
        "LINKED_TO",
        {"weight": 0.5}
    )
    logger.info(f"Nodes linked: {linked}")
    
    # 5. Traverse
    neighbors = await driver.traverse(
        "TestNode", {"id": "test_1"},
        rel_type="LINKED_TO",
        target_label="TargetNode"
    )
    logger.info(f"Traversed to: {neighbors}")
    assert len(neighbors) == 1
    assert neighbors[0]["id"] == "target_1"
    
    # 6. Vector Search
    await driver.upsert_node("TestNode", "id", {"id": "v_1", "embedding": [1.0, 0.0, 0.0], "name": "Vector A"})
    await driver.upsert_node("TestNode", "id", {"id": "v_2", "embedding": [0.0, 1.0, 0.0], "name": "Vector B"})
    
    similar = await driver.search_similar("TestNode", [0.9, 0.1, 0.0], top_k=1)
    logger.info(f"Vector search results: {len(similar)}")
    assert len(similar) == 1
    assert similar[0]["id"] == "v_1"
    
    # 7. Delete
    await driver.delete_nodes("TestNode", {"id": "v_1"})
    await driver.delete_nodes("TestNode", {"id": "v_2"})
    deleted = await driver.delete_nodes("TestNode", {"id": "test_1"})
    logger.info(f"Deleted nodes: {deleted}")
    
    logger.info(f"--- Driver {driver.__class__.__name__} PASSED ---")

async def test_memory_integration():
    logger.info("--- Testing GraphMemoryStorage Integration ---")
    storage = GraphMemoryStorage()
    await storage.initialize()
    
    # Create a Concept
    entry = MemoryEntry(
        title="Unified Graph Theory",
        content="Everything is a node.",
        type=MemoryType.CONCEPT,
        project_id=999
    )
    
    await storage.save(entry)
    logger.info(f"Saved memory entry: {entry.id}")
    
    # Retrieve
    retrieved = await storage.get(entry.id)
    logger.info(f"Retrieved entry: {retrieved.title if retrieved else 'None'}")
    assert retrieved is not None
    assert retrieved.type == MemoryType.CONCEPT
    
    # Search
    results = await storage.search(query="Unified", project_id=999)
    logger.info(f"Search results: {len(results)}")
    assert len(results) >= 1
    
    # Vector Search
    v_results = await storage.search_similar(query_embedding=[1.0] * 1536, top_k=1, project_id=999)
    logger.info(f"Vector search results: {len(v_results)}")
    # Note: Our test entry doesn't have embedding in save() yet, 
    # but we can manually upsert one for the test.
    await storage._driver.upsert_node(
        "Concept", "id", {"id": entry.id, "embedding": [1.0] * 1536}
    )
    v_results = await storage.search_similar(query_embedding=[1.0] * 1536, top_k=1, project_id=999)
    assert len(v_results) == 1
    logger.info("Vector memory search PASSED")
    
    # Clean up
    await storage.delete(entry.id)
    logger.info("Memory integration PASSED")

async def main():
    # Force Embedded Mode for FileGraph test
    settings.EMBEDDED_MODE = True
    file_driver = GraphManager.get_driver()
    await test_driver_parity(file_driver)
    
    # Integration test (uses whatever driver is active, currently file)
    await test_memory_integration()
    
    logger.info("\n✅ ALL GRAPH ARCHITECTURE TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(main())
