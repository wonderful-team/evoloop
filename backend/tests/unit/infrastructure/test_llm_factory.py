"""
Unit tests for LLM factory.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestLLMFactory:
    """Tests for LLMFactory."""

    def test_llm_factory_imports(self):
        """Test that LLM factory can be imported."""
        from app.infrastructure.llm.factory import LLMFactory, get_default_llm
        assert LLMFactory is not None
        assert get_default_llm is not None

    def test_llm_factory_has_create_method(self):
        """Test that LLMFactory has create_llm method."""
        from app.infrastructure.llm.factory import LLMFactory
        assert hasattr(LLMFactory, 'create_llm')

    def test_llm_factory_has_completion_method(self):
        """Test that LLMFactory has create_completion_client method."""
        from app.infrastructure.llm.factory import LLMFactory
        assert hasattr(LLMFactory, 'create_completion_client')


class TestLLMFactoryMocked:
    """Mocked tests for LLMFactory."""

    @patch('app.infrastructure.config.service.SystemConfigService')
    @patch('app.infrastructure.llm.factory.AdaptiveChatOpenAI')
    def test_create_llm_basic(self, mock_adaptive, mock_config):
        """Test creating basic LLM."""
        mock_config.get_value.side_effect = lambda key: {
            "LLM_PROVIDER": "openai",
            "LLM_BASE_URL": "https://api.openai.com",
            "LLM_MODEL": "gpt-4",
            "LLM_API_KEY": "test-key"
        }.get(key)

        mock_llm = MagicMock()
        mock_adaptive.return_value = mock_llm

        from app.infrastructure.llm.factory import LLMFactory
        result = LLMFactory.create_llm()

        assert result == mock_llm


class TestGetDefaultLLM:
    """Tests for get_default_llm function."""

    @patch('app.infrastructure.llm.factory.LLMFactory.create_llm')
    def test_get_default_llm(self, mock_create):
        """Test get_default_llm calls factory."""
        mock_llm = MagicMock()
        mock_create.return_value = mock_llm

        from app.infrastructure.llm.factory import get_default_llm
        result = get_default_llm(temperature=0.5)

        assert result == mock_llm
        mock_create.assert_called_once_with(temperature=0.5)
