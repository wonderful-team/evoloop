"""
Verify that LLMFactory routes to _create_direct_llm when LLM_BASE_URL
is set in the database, even if the model name has no custom- prefix.

This tests the fallback added in factory.py:190-205.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.schemas import LLMConfig


class TestLLMFactoryDBFallbackRouting:
    @pytest.fixture(autouse=True)
    def clear_factory_cache(self):
        from app.infrastructure.llm.factory import LLMFactory

        LLMFactory.clear_cache()
        yield
        LLMFactory.clear_cache()

    @pytest.mark.asyncio
    async def test_plain_model_name_routes_to_direct_when_db_base_url_set(self):
        """Plain model name (no custom- prefix) should route to _create_direct_llm
        when LLM_BASE_URL is configured in the database."""
        from app.infrastructure.llm.factory import LLMFactory

        fake_instance = {"mock": "direct-llm"}

        with (
            patch.object(
                LLMFactory,
                "_create_direct_llm",
                return_value=fake_instance,
            ) as mock_direct,
            patch.object(
                LLMFactory,
                "_create_platform_llm",
                return_value=None,
            ) as mock_platform,
            patch(
                "app.infrastructure.config.service.SystemConfigService.get_value",
            ) as mock_get_value,
        ):
            def side_effect(key, default=None):
                if key == "LLM_BASE_URL":
                    return "https://custom-api.example.com/v1"
                if key == "LLM_API_KEY":
                    return "sk-custom-key"
                if key == "LLM_PROVIDER_TYPE":
                    return "openai"
                return None

            mock_get_value.side_effect = side_effect

            config = LLMConfig(model_name="gpt-4")
            instance = await LLMFactory.create_llm(config)

            assert instance is fake_instance
            mock_direct.assert_called_once()
            mock_platform.assert_not_called()

    @pytest.mark.asyncio
    async def test_plain_model_name_routes_to_platform_when_no_db_base_url(self):
        """Plain model name should route to _create_platform_llm when DB has no
        LLM_BASE_URL configured (default behavior)."""
        from app.infrastructure.llm.factory import LLMFactory

        fake_instance = {"mock": "platform-llm"}

        with (
            patch.object(
                LLMFactory,
                "_create_direct_llm",
                return_value=None,
            ) as mock_direct,
            patch.object(
                LLMFactory,
                "_create_platform_llm",
                return_value=fake_instance,
            ) as mock_platform,
        ):
            config = LLMConfig(model_name="gpt-4")
            instance = await LLMFactory.create_llm(config)

            assert instance is fake_instance
            mock_platform.assert_called_once()
            mock_direct.assert_not_called()

    @pytest.mark.asyncio
    async def test_custom_prefix_still_routes_to_custom(self):
        """custom-* model names should still route to _create_custom_llm,
        unaffected by the new fallback."""
        from app.infrastructure.llm.factory import LLMFactory

        fake_instance = {"mock": "custom-llm"}

        with (
            patch.object(
                LLMFactory,
                "_create_custom_llm",
                return_value=fake_instance,
            ) as mock_custom,
            patch.object(
                LLMFactory,
                "_create_platform_llm",
                return_value=None,
            ) as mock_platform,
            patch.object(
                LLMFactory,
                "_create_direct_llm",
                return_value=None,
            ) as mock_direct,
            patch(
                "app.infrastructure.config.service.SystemConfigService.get_value",
            ) as mock_get_value,
        ):
            mock_get_value.return_value = None

            config = LLMConfig(model_name="custom-openai-gpt-4")
            instance = await LLMFactory.create_llm(config)

            assert instance is fake_instance
            mock_custom.assert_called_once()
            mock_direct.assert_not_called()
            mock_platform.assert_not_called()

    @pytest.mark.asyncio
    async def test_direct_config_base_url_still_routes_to_direct(self):
        """Explicit base_url on LLMConfig should still route to _create_direct_llm
        via the existing elif branch, unaffected by the new fallback."""
        from app.infrastructure.llm.factory import LLMFactory

        fake_instance = {"mock": "direct-llm"}

        with (
            patch.object(
                LLMFactory,
                "_create_direct_llm",
                return_value=fake_instance,
            ) as mock_direct,
            patch.object(
                LLMFactory,
                "_create_platform_llm",
                return_value=None,
            ) as mock_platform,
        ):
            config = LLMConfig(
                model_name="gpt-4",
                base_url="https://explicit.example.com/v1",
            )
            instance = await LLMFactory.create_llm(config)

            assert instance is fake_instance
            mock_direct.assert_called_once()
            mock_platform.assert_not_called()
