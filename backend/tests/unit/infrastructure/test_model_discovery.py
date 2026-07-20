"""Tests for ModelDiscoveryService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.llm.discovery import DiscoveredModel, ModelDiscoveryService


@pytest.mark.asyncio
async def test_discover_lm_studio():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": "qwen3-4b"},
            {"id": "text-embedding-nomic"},
        ]
    }

    async def mock_get(*args, **kwargs):
        return mock_response

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        models = await ModelDiscoveryService._probe_lm_studio()
        assert len(models) == 2
        assert models[0].source == "lm-studio"
        assert models[0].model_name == "qwen3-4b"
        assert models[0].base_url == "http://localhost:1234/v1"


@pytest.mark.asyncio
async def test_discover_lm_studio_unavailable():
    async def mock_get(*args, **kwargs):
        raise ConnectionError("Connection refused")

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        models = await ModelDiscoveryService._probe_lm_studio()
        assert models == []


@pytest.mark.asyncio
async def test_discover_ollama():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "models": [
            {"name": "llama3.2:latest"},
            {"name": "nomic-embed-text:latest"},
        ]
    }

    async def mock_get(*args, **kwargs):
        return mock_response

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        models = await ModelDiscoveryService._probe_ollama()
        assert len(models) == 2
        assert models[0].source == "ollama"
        assert models[0].model_name == "llama3.2:latest"
        assert models[0].base_url == "http://localhost:11434/v1"


@pytest.mark.asyncio
async def test_discover_ollama_unavailable():
    async def mock_get(*args, **kwargs):
        raise ConnectionError("Connection refused")

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        models = await ModelDiscoveryService._probe_ollama()
        assert models == []


@pytest.mark.asyncio
async def test_discover_gguf(tmp_path):
    gguf_dir = tmp_path / "gguf"
    gguf_dir.mkdir()
    (gguf_dir / "qwen3-4b-instruct.gguf").write_bytes(b"fake")
    (gguf_dir / "bge-base-zh-v1.5.gguf").write_bytes(b"fake")

    with patch.dict("os.environ", {"LIGHTNING_GGUF_DIR": str(gguf_dir)}):
        models = await ModelDiscoveryService._probe_gguf_dir()
        assert len(models) == 2
        names = {m.model_name for m in models}
        assert any("qwen3-4b-instruct" in n for n in names)


@pytest.mark.asyncio
async def test_discover_gguf_empty(tmp_path):
    gguf_dir = tmp_path / "empty_gguf"
    gguf_dir.mkdir()
    with patch.dict("os.environ", {"LIGHTNING_GGUF_DIR": str(gguf_dir)}):
        models = await ModelDiscoveryService._probe_gguf_dir()
        assert models == []


@pytest.mark.asyncio
async def test_discover_all_aggregates():
    mock_lm = MagicMock()
    mock_lm.status_code = 200
    mock_lm.json.return_value = {"data": [{"id": "test-model"}]}

    mock_ollama = MagicMock()
    mock_ollama.status_code = 200
    mock_ollama.json.return_value = {"models": [{"name": "test-ollama"}]}

    call_count = [0]

    async def mock_get(url, **kwargs):
        call_count[0] += 1
        if "lm-studio" in url or "localhost:1234" in url:
            return mock_lm
        if "ollama" in url or "localhost:11434" in url:
            return mock_ollama
        raise ValueError(f"Unexpected URL: {url}")

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        with patch.object(
            ModelDiscoveryService, "_probe_gguf_dir", return_value=[]
        ):
            with patch.object(
                ModelDiscoveryService, "_probe_custom_config", return_value=[]
            ):
                models = await ModelDiscoveryService.discover_all()
                assert len(models) == 2
                sources = {m.source for m in models}
                assert sources == {"lm-studio", "ollama"}


@pytest.mark.asyncio
async def test_discover_dedup():
    """discover_all should deduplicate models with the same id."""
    mock_lm = MagicMock()
    mock_lm.status_code = 200
    mock_lm.json.return_value = {"data": [{"id": "shared-model"}]}

    mock_ollama = MagicMock()
    mock_ollama.status_code = 200
    mock_ollama.json.return_value = {"models": [{"name": "shared-model"}]}

    async def mock_get(url, **kwargs):
        if "lm-studio" in url or "localhost:1234" in url:
            return mock_lm
        return mock_ollama

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        with patch.object(ModelDiscoveryService, "_probe_gguf_dir", return_value=[]):
            with patch.object(ModelDiscoveryService, "_probe_custom_config", return_value=[]):
                models = await ModelDiscoveryService.discover_all()
                # lm-studio:shared-model and ollama:shared-model are different IDs
                assert len(models) == 2
