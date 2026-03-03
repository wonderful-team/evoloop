import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.domain.codebase.indexing.service import IndexingService

# Add project root to path
sys.path.append(os.getcwd())


# --- Mock Embedder ---
class MockEmbedder:
    async def embed_query(self, text):
        return [0.1] * 1536
    
    async def embed_documents(self, texts):
        return [[0.1] * 1536 for _ in texts]
    
    async def aembed_query(self, text):
        return [0.1] * 1536
    
    async def aembed_documents(self, texts):
        return [[0.1] * 1536 for _ in texts]


async def seed_data():
    print("=== Seeding Test Data ===")
    print(f"Workspace Root: {settings.WORKSPACE_ROOT}")

    if not settings.WORKSPACE_ROOT:
        print(f"❌ Error: WORKSPACE_ROOT not configured!")
        return

    if not os.path.exists(settings.WORKSPACE_ROOT):
        print(f"❌ Error: Workspace root {settings.WORKSPACE_ROOT} does not exist!")
        return

    # Patch Factory to return MockEmbedder
    with patch("app.domain.codebase.indexing.vectors.factory.EmbedderFactory.get_embedder", return_value=MockEmbedder()):
        service = IndexingService()

        # Scan subdirectories
        for item in os.listdir(settings.WORKSPACE_ROOT):
            path = os.path.join(settings.WORKSPACE_ROOT, item)
            if os.path.isdir(path) and not item.startswith("."):
                print(f"📦 Found Project: {item}")
                
                # 1. Register Repository
                # This might trigger SystemConfig query internally (now fixed)
                try:
                    repo = await service.get_or_create_repo(
                        path=path,
                        name=item,
                        project_id=7 # Mock Project ID
                    )
                    print(f"   └── Registered Repository ID: {repo.id}")
                    
                    # 2. Trigger Indexing
                    print(f"   └── Indexing files...")
                    await service.index_repository(repo.local_path, repo.id, force=True)
                    print(f"   ✅ Indexed.")
                    
                except Exception as e:
                    print(f"   ❌ Failed to process {item}: {e}")
                    import traceback
                    traceback.print_exc()

    print("=== Seeding Complete ===")


if __name__ == "__main__":
    asyncio.run(seed_data())
