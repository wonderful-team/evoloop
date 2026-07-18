import os
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.infrastructure.embeddings.local import LocalEmbedder


@pytest.fixture(autouse=True)
def reset_local_embedder_cache():
    LocalEmbedder._shared_model_cache.clear()
    yield
    LocalEmbedder._shared_model_cache.clear()


@pytest.mark.asyncio
async def test_local_embedder_llamacpp():
    embedder = LocalEmbedder(model_path="/mock/model.gguf")

    mock_llama_instance = MagicMock()
    mock_llama_instance.create_embedding.return_value = {
        "data": [{"embedding": [0.1, 0.2, 0.3], "index": 0}]
    }

    with patch("llama_cpp.Llama", return_value=mock_llama_instance) as mock_llama_class:
        model = await embedder._get_model()
        assert model == mock_llama_instance
        mock_llama_class.assert_called_once_with(
            model_path="/mock/model.gguf",
            embedding=True,
            n_ctx=512,
            n_threads=2,
            n_gpu_layers=0,
            verbose=False,
        )

        query_res = await embedder.embed_query("test query")
        assert query_res == [0.1, 0.2, 0.3]

        mock_llama_instance.create_embedding.return_value = {
            "data": [
                {"embedding": [0.1, 0.2, 0.3], "index": 0},
                {"embedding": [0.4, 0.5, 0.6], "index": 1},
            ]
        }
        docs_res = await embedder.embed_documents(["doc1", "doc2"])
        assert docs_res == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
