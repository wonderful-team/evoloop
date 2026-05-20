import asyncio
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("TopLevelVerify")

async def test_top_level_flow():
    """
    Test the full flow: Indexing -> Tool Calling -> Result Verification
    """
    from app.domain.codebase.indexing.components.graph_syncer import GraphSyncer
    from app.domain.codebase.indexing.components.graph_syncer import GraphSyncer
    from app.domain.codebase.schemas import IndexedContent, ExtractedEntity
    from app.domain.codebase.indexing.components.file_preparer import PreparedFile
    from app.domain.codebase.retrieval.tools import search_codebase
    from app.infrastructure.database.graph.driver import GraphManager
    from app.models.schemas.document import Document

    logger.info("=== Starting Top-Level Graph Verification ===")

    # 1. Setup Mock Data
    project_id = 999
    file_path = "top_level_test.py"
    full_name = "top_level_test.run_verify"
    
    # Mock Objects
    class MockRepo:
        id = 999
        project_id = 999
        
    class MockFile:
        id = 1
        path = "top_level_test.py"

    class MockPreparedFile:
        repo = MockRepo()
        rel_path = "top_level_test.py"
        file_path = "top_level_test.py"

    prepared = MockPreparedFile()
    
    # Mock IndexedContent
    indexed = IndexedContent(
        documents=[Document(content="test", metadata={"type":"file", "name":"test"})],
        entities=[
            ExtractedEntity(name="run_verify", full_name=full_name, type="function", start_line=1, end_line=10)
        ],
        relations=[],
        embeddings=[[0.1]*768],
        file_summary_doc=Document(content="summary", metadata={"type":"file", "name":"summary"})
    )

    # 2. Simulate Indexing (GraphSyncer)
    logger.info(f"Step 1: Simulating Indexing for {file_path}...")
    syncer = GraphSyncer()
    await syncer.sync(
        prepared=prepared,
        indexed=indexed,
        file_line_count=10,
        source_file_pg_id=1,
        entity_pg_ids={full_name: 1}
    )

    # Verify indexing result in driver
    driver = GraphManager.get_driver()
    nodes = await driver.find_nodes("CodeEntity", {"name": "run_verify", "project_id": project_id})
    if not nodes:
        logger.error("❌ Indexing Verification Failed: CodeEntity node not found in graph.")
        return
    logger.info(f"✅ Indexing Verified: Found {len(nodes)} node(s) for 'run_verify'")

    # 3. Simulate Tool Call (search_codebase)
    # This is the top-level entry point used by the Agent
    logger.info(f"Step 2: Calling search_codebase tool for '{full_name}'...")
    
    # We use a substring that matches our indexed entity
    # search_codebase is a LangChain tool, use .ainvoke()
    tool_result = await search_codebase.ainvoke({
        "query": "run_verify", 
        "operator": "and", 
        "project_id": project_id
    })
    
    # ToolResult inherits from str, so tool_result itself is the result_str
    result_str = str(tool_result)
    metadata = getattr(tool_result, "meta", {})
    
    logger.info(f"Tool Metadata: {metadata}")
    logger.info(f"Tool Output Preview:\n{result_str[:200]}...")

    # 4. Verify Tool Output
    if "run_verify" in result_str and "top_level_test.py" in result_str:
        logger.info("✅ Tool Call Verified: Agent output contains indexed symbol and file path.")
    else:
        logger.error("❌ Tool Call Verification Failed: Agent output missing expected symbol info.")
        logger.error(f"Actual output: {result_str}")
        return

    # 5. Cleanup (Optional but good practice)
    # We leave the nodes for manual inspection if needed, or clear them
    # await driver.delete_nodes("CodeEntity", {"project_id": project_id})
    # await driver.delete_nodes("File", {"project_id": project_id})

    logger.info("=== Top-Level Verification PASSED ===")

if __name__ == "__main__":
    asyncio.run(test_top_level_flow())
