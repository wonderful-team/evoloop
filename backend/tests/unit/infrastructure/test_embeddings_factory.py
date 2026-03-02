"""
Unit tests for Embeddings factory.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.infrastructure.embeddings.factory import EmbedderFactory


class TestEmbedderFactory:
    """Tests for EmbedderFactory."""

    @patch('app.infrastructure.embeddings.factory.SystemConfigService')
    @patch('app.infrastructure.embeddings.factory.GenericOpenAIEmbedder')
    def test_get_embedder_openai_from_config(self, mock_embedder_class, mock_config):
        """Test getting OpenAI embedder from system config."""
        mock_config.get_value.side_effect = lambda key: {
            "EMBEDDING_PROVIDER": "openai",
            "EMBEDDING_BASE_URL": "https://api.openai.com",
            "EMBEDDING_MODEL": "text-embedding-3-small",
            "EMBEDDING_API_KEY": "test-key",
            "EMBEDDING_DIMENSIONS": "1536"
        }.get(key)

        mock_embedder = MagicMock()
        mock_embedder_class.return_value = mock_embedder

        result = EmbedderFactory.get_embedder()

        assert result == mock_embedder
        mock_embedder_class.assert_called_once()
        call_kwargs = mock_embedder_class.call_args.kwargs
        assert call_kwargs['api_key'] == "test-key"
        assert call_kwargs['base_url'] == "https://api.openai.com"
        assert call_kwargs['model'] == "text-embedding-3-small"
        assert call_kwargs['dimensions'] == 1536

    @patch('app.infrastructure.embeddings.factory.SystemConfigService')
    @patch('app.infrastructure.embeddings.factory.OllamaEmbedder')
    def test_get_embedder_ollama(self, mock_embedder_class, mock_config):
        """Test getting Ollama embedder."""
        mock_config.get_value.side_effect = lambda key: {
            "EMBEDDING_PROVIDER": "ollama",
            "EMBEDDING_BASE_URL": "http://localhost:11434",
            "EMBEDDING_MODEL": "nomic-embed-text"
        }.get(key)

        mock_embedder = MagicMock()
        mock_embedder_class.return_value = mock_embedder

        result = EmbedderFactory.get_embedder()

        assert result == mock_embedder
        mock_embedder_class.assert_called_once_with(
            base_url="http://localhost:11434",
            model="nomic-embed-text"
        )

    @patch('app.infrastructure.embeddings.factory.SystemConfigService')
    @patch('app.infrastructure.embeddings.factory.OllamaEmbedder')
    def test_get_embedder_ollama_defaults(self, mock_embedder_class, mock_config):
        """Test getting Ollama embedder with defaults."""
        mock_config.get_value.side_effect = lambda key: {
            "EMBEDDING_PROVIDER": "ollama",
            "EMBEDDING_BASE_URL": None,
            "EMBEDDING_MODEL": None
        }.get(key)

        mock_embedder = MagicMock()
        mock_embedder_class.return_value = mock_embedder

        result = EmbedderFactory.get_embedder()

        mock_embedder_class.assert_called_once_with(
            base_url="http://localhost:11434",
            model="nomic-embed-text"
        )

    @patch('app.infrastructure.embeddings.factory.SystemConfigService')
    @patch('app.infrastructure.embeddings.factory.GenericOpenAIEmbedder')
    def test_get_embedder_generic_provider(self, mock_embedder_class, mock_config):
        """Test getting embedder with generic provider."""
        mock_config.get_value.side_effect = lambda key: {
            "EMBEDDING_PROVIDER": "generic",
            "EMBEDDING_BASE_URL": "https://api.example.com",
            "EMBEDDING_MODEL": "embedding-model",
            "EMBEDDING_API_KEY": "test-key",
            "EMBEDDING_DIMENSIONS": "768"
        }.get(key)

        mock_embedder = MagicMock()
        mock_embedder_class.return_value = mock_embedder

        result = EmbedderFactory.get_embedder()

        assert result == mock_embedder

    @patch('app.infrastructure.embeddings.factory.SystemConfigService')
    def test_get_embedder_unknown_provider(self, mock_config):
        """Test getting embedder with unknown provider raises error."""
        mock_config.get_value.side_effect = lambda key: {
            "EMBEDDING_PROVIDER": "unknown_provider"
        }.get(key)

        with pytest.raises(ValueError, match="Unknown Embedding Provider"):
            EmbedderFactory.get_embedder()

    @patch('app.infrastructure.embeddings.factory.SystemConfigService')
    @patch('app.infrastructure.embeddings.factory.GenericOpenAIEmbedder')
    @patch('app.infrastructure.embeddings.factory.settings')
    def test_get_embedder_fallback_to_settings(self, mock_settings, mock_embedder_class, mock_config):
        """Test getting embedder falls back to settings when no DB config."""
        mock_config.get_value.return_value = None
        mock_settings.EMBEDDING_DIMENSIONS = 768
        mock_settings.OPENAI_BASE_URL = "https://api.openai.com"
        mock_settings.OPENAI_API_KEY = "fallback-key"
        mock_settings.EMBEDDING_MODEL_NAME = "text-embedding-ada-002"

        mock_embedder = MagicMock()
        mock_embedder_class.return_value = mock_embedder

        result = EmbedderFactory.get_embedder()

        assert result == mock_embedder
        mock_embedder_class.assert_called_once()
        call_kwargs = mock_embedder_class.call_args.kwargs
        assert call_kwargs['api_key'] == "fallback-key"

    @patch('app.infrastructure.embeddings.factory.SystemConfigService')
    @patch('app.infrastructure.embeddings.factory.GenericOpenAIEmbedder')
    @patch('app.infrastructure.embeddings.factory.settings')
    def test_get_embedder_local_lmstudio(self, mock_settings, mock_embedder_class, mock_config):
        """Test getting embedder detects local LMStudio."""
        mock_config.get_value.return_value = None
        mock_settings.EMBEDDING_DIMENSIONS = 768
        mock_settings.OPENAI_BASE_URL = "http://localhost:1234/v1"
        mock_settings.OPENAI_API_KEY = "lmstudio-key"
        mock_settings.EMBEDDING_MODEL_NAME = "local-model"

        mock_embedder = MagicMock()
        mock_embedder_class.return_value = mock_embedder

        result = EmbedderFactory.get_embedder()

        assert result == mock_embedder
        call_kwargs = mock_embedder_class.call_args.kwargs
        assert "localhost" in call_kwargs['base_url']
