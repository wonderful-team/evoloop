"""Unit tests for the generation client factory
(app/infrastructure/vision/generation.py).

Covers the gateway auth flow used on the image/video generation user path.
`evocloud_manager` is imported at module top-level in generation.py, so we
patch the module's own reference via monkeypatch.setattr(gen_mod, ...).
"""

from types import SimpleNamespace

import pytest

from app.infrastructure.vision import generation as gen_mod


class TestGatewayBaseUrl:
    def test_returns_url_when_configured(self, monkeypatch):
        monkeypatch.setattr(
            gen_mod, "evocloud_manager",
            SimpleNamespace(api=SimpleNamespace(root_url="https://gw.example.com")),
        )
        assert (
            gen_mod._gateway_base_url() == "https://gw.example.com/gateway/v1"
        )

    def test_empty_when_no_api(self, monkeypatch):
        monkeypatch.setattr(gen_mod, "evocloud_manager", SimpleNamespace(api=None))
        assert gen_mod._gateway_base_url() == ""


class TestIsGatewayConfigured:
    def test_true_when_configured(self, monkeypatch):
        monkeypatch.setattr(
            gen_mod, "evocloud_manager",
            SimpleNamespace(api=SimpleNamespace(root_url="https://gw.example.com")),
        )
        assert gen_mod.is_gateway_configured() is True

    def test_false_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(gen_mod, "evocloud_manager", SimpleNamespace(api=None))
        assert gen_mod.is_gateway_configured() is False


class TestCreateGenerationClient:
    def test_raises_when_gateway_missing(self, monkeypatch):
        monkeypatch.setattr(gen_mod, "evocloud_manager", SimpleNamespace(api=None))
        with pytest.raises(ValueError, match="Gateway URL not configured"):
            gen_mod.create_generation_client()

    def test_returns_async_openai_with_pooled_client(self, monkeypatch):
        monkeypatch.setattr(
            gen_mod, "evocloud_manager",
            SimpleNamespace(api=SimpleNamespace(root_url="https://gw.example.com")),
        )

        fake_pool = SimpleNamespace(get=lambda: SimpleNamespace(closed=False))
        monkeypatch.setattr(
            "app.infrastructure.llm.factory.HTTP_CLIENT_POOL", fake_pool
        )

        created = {}

        class _FakeAsyncOpenAI:
            def __init__(self, **kwargs):
                created.update(kwargs)

        # generation.py 内 `import openai` 拿到全局 openai 模块 → patch 其 AsyncOpenAI
        import openai as openai_mod

        monkeypatch.setattr(openai_mod, "AsyncOpenAI", _FakeAsyncOpenAI)

        client = gen_mod.create_generation_client()
        assert created.get("base_url") == "https://gw.example.com/gateway/v1"
        assert created.get("http_client") is not None
        assert client is not None
