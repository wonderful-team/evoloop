"""Unit tests for LLMFactory custom-fallback gating.

Covers the factory.py decision about whether a stale LLM_BASE_URL in the system
config may hijack an otherwise-platform request. After the platform-mode change,
the DB fallback is only allowed when LLM_CONFIG_TYPE == "custom"; otherwise the
request must go to the gateway (which assigns a default model remotely).
"""

from types import SimpleNamespace

import pytest

from app.infrastructure.llm import factory as factory_mod


@pytest.fixture
def systems_cfg(monkeypatch):
    """Redirect SystemConfigService.get_value to an in-test dict."""
    values: dict[str, str] = {}

    def _get(key, default=None):
        return values.get(key, default)

    monkeypatch.setattr(
        factory_mod.SystemConfigService, "get_value", staticmethod(_get)
    )
    return values


@pytest.fixture
def clear_factory_cache():
    factory_mod.LLMFactory.clear_cache()
    yield
    factory_mod.LLMFactory.clear_cache()


async def _fake_platform(config):
    return SimpleNamespace(created="platform", model=config.model_name)


async def _fake_custom(config):
    return SimpleNamespace(created="custom", model=config.model_name)


class TestPlatformModeBypassesStaleBaseUrl:
    @pytest.mark.asyncio
    async def test_platform_ignores_db_base_url(
        self, systems_cfg, clear_factory_cache, monkeypatch
    ):
        """platform mode with a stale LLM_BASE_URL in DB must still route to the
        gateway, not the old custom endpoint."""
        systems_cfg["LLM_CONFIG_TYPE"] = "platform"
        systems_cfg["LLM_BASE_URL"] = "https://stale.example.com"
        systems_cfg["LLM_API_KEY"] = "old-key"

        monkeypatch.setattr(factory_mod.LLMFactory, "_create_platform_llm", _fake_platform)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_direct_llm", _fake_custom)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_custom_llm", _fake_custom)

        llm = await factory_mod.LLMFactory.create_llm()
        assert llm.created == "platform"

    @pytest.mark.asyncio
    async def test_platform_with_model_name_still_goes_gateway(
        self, systems_cfg, clear_factory_cache, monkeypatch
    ):
        """Even a named model in platform mode is routed through the gateway —
        a stale base_url must not pull it to direct."""
        systems_cfg["LLM_CONFIG_TYPE"] = "platform"
        systems_cfg["LLM_BASE_URL"] = "https://stale.example.com"

        monkeypatch.setattr(factory_mod.LLMFactory, "_create_platform_llm", _fake_platform)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_direct_llm", _fake_custom)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_custom_llm", _fake_custom)

        llm = await factory_mod.LLMFactory.create_llm(model_name="deepseek-v4")
        assert llm.created == "platform"


class TestCustomModeAllowsDbFallback:
    @pytest.mark.asyncio
    async def test_custom_uses_db_base_url(
        self, systems_cfg, clear_factory_cache, monkeypatch
    ):
        """custom mode without an explicit base_url on the call may fall back to
        the DB base_url (legacy behavior preserved for existing setups)."""
        systems_cfg["LLM_CONFIG_TYPE"] = "custom"
        systems_cfg["LLM_BASE_URL"] = "https://custom.example.com"
        systems_cfg["LLM_API_KEY"] = "custom-key"
        systems_cfg["LLM_PROVIDER_TYPE"] = "openai"

        seen = {}

        async def _capture_direct(config):
            seen["direct"] = config
            return SimpleNamespace(created="direct", model=config.model_name)

        monkeypatch.setattr(factory_mod.LLMFactory, "_create_platform_llm", _fake_platform)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_direct_llm", _capture_direct)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_custom_llm", _fake_custom)

        llm = await factory_mod.LLMFactory.create_llm(model_name="my-llm")
        assert llm.created == "direct"
        assert seen["direct"].base_url == "https://custom.example.com"

    @pytest.mark.asyncio
    async def test_custom_empty_model_falls_back_to_db_model(
        self, systems_cfg, clear_factory_cache, monkeypatch
    ):
        systems_cfg["LLM_CONFIG_TYPE"] = "custom"
        systems_cfg["LLM_BASE_URL"] = "https://custom.example.com"
        systems_cfg["LLM_API_KEY"] = "custom-key"
        systems_cfg["LLM_PROVIDER_TYPE"] = "openai"
        systems_cfg["CUSTOM_LLM_MODEL"] = "default-model"

        seen = {}

        async def _capture_direct(config):
            seen["direct"] = config
            return SimpleNamespace(created="direct", model=config.model_name)

        monkeypatch.setattr(factory_mod.LLMFactory, "_create_platform_llm", _fake_platform)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_direct_llm", _capture_direct)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_custom_llm", _fake_custom)

        llm = await factory_mod.LLMFactory.create_llm()
        assert llm.created == "direct"
        assert seen["direct"].model_name == "default-model"


class TestCustomModelIdShortCircuit:
    @pytest.mark.asyncio
    async def test_custom_prefix_routes_to_custom_model(
        self, systems_cfg, clear_factory_cache, monkeypatch
    ):
        """Explicit custom-* ids must always go through _create_custom_llm,
        regardless of LLM_CONFIG_TYPE."""
        systems_cfg["LLM_CONFIG_TYPE"] = "platform"
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_platform_llm", _fake_platform)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_custom_llm", _fake_custom)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_direct_llm", _fake_custom)

        llm = await factory_mod.LLMFactory.create_llm(
            model_name="custom-openai-gpt-4o",
            base_url="https://api.openai.com",
            api_key="sk-test",
        )
        assert llm.created == "custom"


class TestMissingConfigTypeDefaultsToPlatform:
    @pytest.mark.asyncio
    async def test_absent_config_type_with_stale_base_url_goes_gateway(
        self, systems_cfg, clear_factory_cache, monkeypatch
    ):
        """When LLM_CONFIG_TYPE is absent (defaults to platform) a stale
        LLM_BASE_URL must not pull the request to direct."""
        systems_cfg["LLM_BASE_URL"] = "https://stale.example.com"

        monkeypatch.setattr(factory_mod.LLMFactory, "_create_platform_llm", _fake_platform)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_direct_llm", _fake_custom)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_custom_llm", _fake_custom)

        llm = await factory_mod.LLMFactory.create_llm(model_name="deepseek-v4")
        assert llm.created == "platform"


class TestExplicitEndpointRoutesDirect:
    @pytest.mark.asyncio
    async def test_explicit_base_url_routes_direct_in_platform_mode(
        self, systems_cfg, clear_factory_cache, monkeypatch
    ):
        """An explicit base_url on the call always routes to direct, even in a
        platform config — the caller pinned a concrete endpoint."""
        systems_cfg["LLM_CONFIG_TYPE"] = "platform"
        systems_cfg["LLM_BASE_URL"] = "https://stale.example.com"

        seen = {}

        async def _capture_direct(config):
            seen["direct"] = config
            return SimpleNamespace(created="direct", model=config.model_name)

        monkeypatch.setattr(factory_mod.LLMFactory, "_create_platform_llm", _fake_platform)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_direct_llm", _capture_direct)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_custom_llm", _fake_custom)

        llm = await factory_mod.LLMFactory.create_llm(
            model_name="my-llm",
            base_url="https://explicit.example.com",
            api_key="sk-explicit",
        )
        assert llm.created == "direct"
        assert seen["direct"].base_url == "https://explicit.example.com"

    @pytest.mark.asyncio
    async def test_api_key_alone_routes_direct(
        self, systems_cfg, clear_factory_cache, monkeypatch
    ):
        """An api_key without a base_url also marks the intent to talk to a
        concrete endpoint rather than the gateway."""
        systems_cfg["LLM_CONFIG_TYPE"] = "platform"

        seen = {}

        async def _capture_direct(config):
            seen["direct"] = config
            return SimpleNamespace(created="direct", model=config.model_name)

        monkeypatch.setattr(factory_mod.LLMFactory, "_create_platform_llm", _fake_platform)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_direct_llm", _capture_direct)
        monkeypatch.setattr(factory_mod.LLMFactory, "_create_custom_llm", _fake_custom)

        llm = await factory_mod.LLMFactory.create_llm(
            model_name="my-llm",
            api_key="sk-only",
        )
        assert llm.created == "direct"
        assert seen["direct"].api_key == "sk-only"
