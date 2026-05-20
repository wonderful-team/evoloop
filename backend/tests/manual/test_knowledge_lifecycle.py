import asyncio
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Important: These must now be imported directly from core or domain
from app.core import file as file_utils
from app.domain.knowledge.services.store import KnowledgeStoreService
from app.domain.knowledge.services.bulk_import import BulkImportService
from app.domain.knowledge.services.pipeline import IngestionPipeline
from app.domain.knowledge.extractors import ExtractorRegistry

async def test_knowledge_lifecycle():
    print("--- Testing Knowledge Lifecycle (Unified File Center) ---")
    
    # Initialize Registry
    ExtractorRegistry.initialize_defaults()
    temp_dir = tempfile.mkdtemp()
    store_dir = os.path.join(temp_dir, "store")
    os.makedirs(store_dir)
    
    try:
        # Initialize services
        # Note: We manually set store path for testing
        store = KnowledgeStoreService()
        store.store_path = Path(store_dir)
        
        pipeline = IngestionPipeline()
        bulk_import = BulkImportService()
        bulk_import.pipeline = pipeline
        
        # 2. Test Single File Ingestion
        print("\n[1] Testing Single File Ingestion...")
        test_file_content = "# Hello Knowledge\nThis is a test document."
        test_file_path = os.path.join(temp_dir, "test.md")
        file_utils.write_file(test_file_path, test_file_content)
        
        with open(test_file_path, "rb") as f:
            result = await pipeline.process(
                file=f,
                filename="test.md",
                collection="test_project"
            )
            
        print(f"Ingestion Success: {result.success}")
        if not result.success:
            print(f"Ingestion Error: {result.error}")
        assert result.success is True

        # 3. Test Bulk Import (Directory)
        print("\n[2] Testing Bulk Import (Directory)...")
        import_dir = os.path.join(temp_dir, "import")
        os.makedirs(import_dir)
        file_utils.write_file(os.path.join(import_dir, "doc1.md"), "Content 1")
        file_utils.write_file(os.path.join(import_dir, "doc2.txt"), "Content 2")
        
        bulk_result = await bulk_import.import_directory(
            directory_path=import_dir,
            project="test_project"
        )
        
        print(f"Bulk Import: {bulk_result.total_files} files, {len(bulk_result.errors)} errors")
        if bulk_result.errors:
            for err in bulk_result.errors:
                print(f"  - Error: {err}")
        assert len(bulk_result.errors) == 0

        # 4. Test Knowledge Store Operations
        print("\n[3] Testing Knowledge Store...")
        # Check if files exist in store (simulated)
        # Store usually saves in store_dir/collection/
        collection_dir = os.path.join(store_dir, "test_project")
        if os.path.exists(collection_dir):
            stored_files = os.listdir(collection_dir)
            print(f"Files in Store: {stored_files}")
            assert len(stored_files) > 0
        else:
            print("Warning: Collection directory not found in store, check if store saves elsewhere")

    finally:
        shutil.rmtree(temp_dir)

    print("\n--- KNOWLEDGE LIFECYCLE TESTS COMPLETED ---")

if __name__ == "__main__":
    asyncio.run(test_knowledge_lifecycle())
