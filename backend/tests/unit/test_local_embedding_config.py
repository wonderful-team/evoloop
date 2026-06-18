import os
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.infrastructure.embeddings.local import LocalEmbedder


@pytest.fixture(autouse=True)
def reset_local_embedder_cache():
    """Each test starts with a clean process-wide model cache."""
    LocalEmbedder._shared_model_cache.clear()
    yield
    LocalEmbedder._shared_model_cache.clear()


def test_settings_hf_endpoint():
    """验证 Settings 能正确加载 HF_ENDPOINT 并设置到 os.environ 中"""
    assert hasattr(settings, "HF_ENDPOINT")
    assert os.environ.get("HF_ENDPOINT") == settings.HF_ENDPOINT


@pytest.mark.asyncio
async def test_local_embedder_asyncio_to_thread():
    """验证 LocalEmbedder 中使用 lambda 包装的 asyncio.to_thread 不会抛出参数数量异常"""
    embedder = LocalEmbedder(model_name="mock-model", device="cpu")

    # 创建一个 mock 的 SentenceTransformer 实例
    mock_st_instance = MagicMock()
    mock_st_instance.encode.return_value = MagicMock(tolist=lambda: [[0.1, 0.2, 0.3]])

    # 当调用 SentenceTransformer 时返回这个实例
    with patch(
        "sentence_transformers.SentenceTransformer", return_value=mock_st_instance
    ) as mock_st_class:
        model = await embedder._get_model()
        assert model == mock_st_instance
        mock_st_class.assert_called_once_with(
            "mock-model", device="cpu", trust_remote_code=True, local_files_only=True
        )

        # 验证 embed_query
        mock_st_instance.encode.return_value = MagicMock(tolist=lambda: [0.1, 0.2, 0.3])
        query_res = await embedder.embed_query("test query")
        assert query_res == [0.1, 0.2, 0.3]

        # 验证 embed_documents
        mock_st_instance.encode.return_value = MagicMock(
            tolist=lambda: [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        )
        docs_res = await embedder.embed_documents(["doc1", "doc2"])
        assert docs_res == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
