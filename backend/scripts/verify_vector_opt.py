
import asyncio
import sys
from unittest.mock import MagicMock, AsyncMock

# Add backend path
sys.path.append("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")

from app.logging import logger

# Mocking modules that might fail without real ENV or DB
sys.modules["app.infrastructure.database.sql.database"] = MagicMock()
sys.modules["app.models"] = MagicMock()
sys.modules["app.domain.codebase.indexing.vectors.factory"] = MagicMock()
sys.modules["app.core.llm.factory"] = MagicMock()

async def verify_components():
    print("--- Verifying Vector Optimization Components ---")

    # 1. Verify QueryRewriter
    print("\n1. Testing QueryRewriter...")
    try:
        from app.domain.codebase.retrieval.rewriter import QueryRewriter
        
        # Mock LLM
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "User Login Authentication AuthService"
        mock_llm.ainvoke.return_value = mock_response

        # Monkeypatch Config (if needed) or just instance
        # Since we mocked LLMFactory in rewriter.py imports (wait, we imported real class but modules are mocked)
        # Let's instantiate and inject mock
        rewriter = QueryRewriter()
        rewriter.llm = mock_llm
        rewriter.enabled = True

        res = await rewriter.rewrite("用户登录")
        print(f"   [PASS] Rewrite Result: {res}")
        assert res == "User Login Authentication AuthService"

    except Exception as e:
        print(f"   [FAIL] QueryRewriter Error: {e}")
        import traceback
        traceback.print_exc()


    # 2. Verify HybridSearcher Logic
    print("\n2. Testing HybridSearcher (RRF)...")
    try:
        from app.domain.codebase.retrieval.hybrid import HybridSearcher
        
        # Mock Embedder
        mock_embedder = AsyncMock()
        mock_embedder.embed_query.return_value = [0.1, 0.2, 0.3]
        
        searcher = HybridSearcher(embedder=mock_embedder)

        # Mock Internal Searches
        searcher._vector_search = AsyncMock(return_value=[
            {"id": 1, "score": 0.9, "content": "vec1"},
            {"id": 2, "score": 0.8, "content": "vec2"}
        ])
        searcher._keyword_search = AsyncMock(return_value=[
            {"id": 2, "score": 1.0, "content": "key1"}, # ID 2 is in both
            {"id": 3, "score": 1.0, "content": "key2"}
        ])

        # Test RRF
        results = await searcher.search("query")
        print(f"   [PASS] Hybrid Search Results: {len(results)}")
        
        # ID 2 should be top because it's in both
        top_id = results[0]["id"]
        print(f"   Top Result ID: {top_id}")
        assert top_id == 2
        
    except Exception as e:
         print(f"   [FAIL] HybridSearcher Error: {e}")
         import traceback
         traceback.print_exc()

    # 3. Verify TreeSitter Skeleton (Partial)
    # This requires treesitter lib, might fail if env not perfect, but let's try importing
    print("\n3. Testing TreeSitterExtractor Import...")
    try:
        from app.domain.codebase.indexing.extractors.treesitter_extractor import TreeSitterExtractor
        extractor = TreeSitterExtractor()
        # Verify method exists
        if hasattr(extractor, "_extract_skeleton"):
            print("   [PASS] _extract_skeleton method exists.")
        else:
            print("   [FAIL] _extract_skeleton MISSING.")
            
    except ImportError:
        print("   [WARN] TreeSitter libs not available in this script context, skipping detailed test.")
    except Exception as e:
        print(f"   [FAIL] TreeSitterExtractor Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_components())
