"""Integration tests for the /system API routes (app/api/routes/system.py).

Exercises the real route layer while mocking service/infrastructure boundaries.
"""

from __future__ import annotations

from types import SimpleNamespace

# ---------------------------------------------------------------------------
# Shared stub helpers
# ---------------------------------------------------------------------------


def _cpu_mem():
    return {
        "cpu_percent": 42.5,
        "mem_percent": 60.0,
        "mem_used": 8 * 1024**3,
        "mem_total": 16 * 1024**3,
    }


def _fake_config(key="k", value="v"):
    return SimpleNamespace(key=key, value=value, description="desc")


async def _set_value_async(key, value, description=None):
    return SimpleNamespace(key=key, value=value, description=description)


def _set_value(key, value, description=None):
    return SimpleNamespace(key=key, value=value, description=description)


async def _validate_connection(*args, **kwargs):
    del args, kwargs
    return True, 1536


async def _validate_llm_connection(*args, **kwargs):
    del args, kwargs
    return True, "pong"


async def _switch_embedding_model(**kwargs):
    del kwargs
    return None


async def _get_available_llm_models(config_type=None):
    del config_type
    return [_llm_model("m1")]


def _llm_model(model_id="m1"):
    return SimpleNamespace(
        id=model_id,
        name="test-llm",
        model="test-model",
        supports_functions=True,
        context_window=8192,
        model_dump=lambda: {
            "id": model_id,
            "name": "test-llm",
            "model": "test-model",
        },
    )


async def _get_available_embedding_models():
    return [
        SimpleNamespace(
            id="e1",
            name="test-embed",
            model="embed-model",
            supports_functions=False,
            context_window=2048,
            model_dump=lambda: {
                "id": "e1",
                "name": "test-embed",
                "model": "embed-model",
            },
        )
    ]


# ---------------------------------------------------------------------------
# System status / config / health
# ---------------------------------------------------------------------------


class TestSystemStatus:
    async def test_get_system_status(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.system.collect_cpu_mem", _cpu_mem
        )
        resp = await client.get("/system/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cpu_percent"] == 42.5
        assert body["ram_percent"] == 60.0
        assert body["status"] == "ok"

    async def test_get_system_status_no_metrics(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.system.collect_cpu_mem", lambda: None)
        resp = await client.get("/system/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cpu_percent"] == 0.0

    async def test_get_system_config(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.system.SystemConfigService",
            SimpleNamespace(
                get_all=lambda: [_fake_config("A", "1"), _fake_config("B", "2")]
            ),
        )
        resp = await client.get("/system/config")
        assert resp.status_code == 200
        data = resp.json()
        # 生产端点在 get_all() 之后追加 MULTI_TENANT_MODE（部署模式暴露给前端）
        assert len(data) == 3
        assert data[0]["key"] == "A"
        assert data[-1]["key"] == "MULTI_TENANT_MODE"

    async def test_health_check(self, client):
        resp = await client.get("/system/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "evoloop-backend"

    async def test_update_system_config(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.system.SystemConfigService",
            SimpleNamespace(set_value_async=_set_value_async),
        )
        resp = await client.post(
            "/system/config", json={"key": "X", "value": "Y"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["key"] == "X"
        assert body["value"] == "Y"


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------


class TestModelDiscovery:
    async def test_discover_models(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.infrastructure.llm.discovery.ModelDiscoveryService",
            SimpleNamespace(discover_all=lambda: _async_return([])),
        )
        monkeypatch.setattr(
            "app.api.routes.system.get_available_llm_models",
            _get_available_llm_models,
        )
        resp = await client.get("/system/models/discover")
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"].startswith("Found")
        assert len(body["models"]) == 1

    async def test_llm_models(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.system.get_available_llm_models",
            _get_available_llm_models,
        )
        resp = await client.get("/system/llm/models")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["models"]) == 1
        assert "last_updated" in body

    async def test_embedding_models(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.system.get_available_embedding_models",
            _get_available_embedding_models,
        )
        resp = await client.get("/system/embedding/models")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["models"]) == 1


# ---------------------------------------------------------------------------
# Customer service duty
# ---------------------------------------------------------------------------


class TestCustomerServiceDuty:
    async def test_get_duty(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.core.channel.duty.config.load_global_duty_config",
            lambda: {"enabled": False, "channels": []},
        )
        resp = await client.get("/system/customer_service_duty")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_validate_duty(self, client, monkeypatch):
        import app.core.channel.duty.provision as provision_mod

        monkeypatch.setattr(
            provision_mod, "validate_global_duty", lambda: _async_return([])
        )
        resp = await client.post("/system/customer_service_duty/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["errors"] == []

    async def test_validate_duty_errors(self, client, monkeypatch):
        import app.core.channel.duty.provision as provision_mod

        monkeypatch.setattr(
            provision_mod,
            "validate_global_duty",
            lambda: _async_return(["wechat not ready"]),
        )
        resp = await client.post("/system/customer_service_duty/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False

    async def test_update_duty_enable(self, client, monkeypatch):
        import app.core.channel.duty.provision as provision_mod

        monkeypatch.setattr(
            "app.core.channel.duty.config.load_global_duty_config",
            lambda: {"enabled": False, "channels": []},
        )
        monkeypatch.setattr(
            "app.core.channel.duty.config.clamp_duty_interval",
            lambda v: v,
        )
        monkeypatch.setattr(
            "app.core.channel.duty.config.save_global_duty_config",
            lambda cfg: None,
        )
        monkeypatch.setattr(
            provision_mod, "validate_global_duty", lambda: _async_return([])
        )
        monkeypatch.setattr(
            provision_mod, "resume_global", lambda: _async_return(None)
        )
        monkeypatch.setattr(
            provision_mod, "stop_global", lambda: _async_return(None)
        )
        resp = await client.put(
            "/system/customer_service_duty",
            json={"enabled": True, "channels": ["wecom"]},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    async def test_update_duty_disable(self, client, monkeypatch):
        import app.core.channel.duty.provision as provision_mod

        monkeypatch.setattr(
            "app.core.channel.duty.config.load_global_duty_config",
            lambda: {"enabled": True, "channels": []},
        )
        monkeypatch.setattr(
            "app.core.channel.duty.config.clamp_duty_interval",
            lambda v: v,
        )
        monkeypatch.setattr(
            "app.core.channel.duty.config.save_global_duty_config",
            lambda cfg: None,
        )
        monkeypatch.setattr(
            provision_mod, "validate_global_duty", lambda: _async_return([])
        )
        monkeypatch.setattr(
            provision_mod, "resume_global", lambda: _async_return(None)
        )
        monkeypatch.setattr(
            provision_mod, "stop_global", lambda: _async_return(None)
        )
        resp = await client.put(
            "/system/customer_service_duty",
            json={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


class TestEmbedding:
    async def test_embedding_tier_status(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.system.SystemConfigService",
            SimpleNamespace(
                get_value=lambda key, default=None: {
                    "EMBEDDING_TIERS": "gguf,local,remote",
                    "EMBEDDING_GGUF_MODEL": "model.gguf",
                    "EMBEDDING_LOCAL_URL": "",
                    "EMBEDDING_PROVIDER": "",
                }.get(key, default),
            ),
        )
        monkeypatch.setattr(
            "app.api.routes.system.EmbedderFactory",
            SimpleNamespace(get_embedder=lambda: SimpleNamespace()),
        )
        resp = await client.get("/system/embedding/tier-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["gguf_available"] is True

    async def test_embedding_tier_apply(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.system.SystemConfigService",
            SimpleNamespace(set_value=_set_value),
        )
        monkeypatch.setattr(
            "app.api.routes.system.EmbedderFactory",
            SimpleNamespace(reset_cache=lambda: None),
        )
        resp = await client.post(
            "/system/embedding/tier-apply",
            json={"tiers": "remote", "provider": "openai", "model": "embed-v1"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"

    async def test_embedding_tier_test_success(self, client, monkeypatch):
        fake_embedder = SimpleNamespace(
            embed_query=lambda s: _async_return([0.1, 0.2, 0.3]),
        )
        monkeypatch.setattr(
            "app.api.routes.system.EmbedderFactory",
            SimpleNamespace(
                reset_cache=lambda: None,
                get_embedder=lambda: fake_embedder,
            ),
        )
        resp = await client.post(
            "/system/embedding/tier-test",
            json={"tiers": "remote"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["dimensions"] == 3

    async def test_embedding_tier_test_no_embedder(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.system.EmbedderFactory",
            SimpleNamespace(
                reset_cache=lambda: None,
                get_embedder=lambda: None,
            ),
        )
        resp = await client.post(
            "/system/embedding/tier-test", json={"tiers": "remote"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False

    async def test_embedding_test(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.system.EmbeddingConfigService",
            SimpleNamespace(validate_connection=_validate_connection),
        )
        resp = await client.post(
            "/system/embedding/test",
            json={
                "provider": "openai",
                "base_url": "https://api.openai.com",
                "model": "text-embedding-3-small",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["dimensions"] == 1536

    async def test_embedding_apply(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.system.EmbeddingConfigService",
            SimpleNamespace(switch_embedding_model=_switch_embedding_model),
        )
        monkeypatch.setattr(
            "app.api.routes.system.SystemConfigService",
            SimpleNamespace(set_value=_set_value),
        )
        monkeypatch.setattr(
            "app.api.routes.system.EmbedderFactory",
            SimpleNamespace(reset_cache=lambda: None),
        )
        resp = await client.post(
            "/system/embedding/apply",
            json={
                "provider": "openai",
                "base_url": "https://api.openai.com",
                "model": "text-embedding-3-small",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"


# ---------------------------------------------------------------------------
# LLM config
# ---------------------------------------------------------------------------


class TestLLMConfig:
    async def test_llm_test(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.system.LLMConfigService",
            SimpleNamespace(validate_connection=_validate_llm_connection),
        )
        resp = await client.post(
            "/system/llm/test",
            json={
                "provider": "openai",
                "model": "gpt-4o",
                "base_url": "https://api.openai.com",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    async def test_llm_apply(self, client, monkeypatch):
        writes: list[tuple[str, str]] = []

        def _capture(key, value, description=None):
            del description
            writes.append((key, value or ""))

        monkeypatch.setattr(
            "app.api.routes.system.SystemConfigService",
            SimpleNamespace(set_value=_capture),
        )
        monkeypatch.setattr(
            "app.api.routes.system.LLMFactory",
            SimpleNamespace(clear_cache=lambda: None),
        )
        resp = await client.post(
            "/system/llm/apply",
            json={
                "provider": "openai",
                "model": "gpt-4o",
                "base_url": "https://api.openai.com",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"
        written = dict(writes)
        # Custom mode persists model provenance keys.
        assert written["LLM_CONFIG_TYPE"] == "custom"
        assert written["LLM_MODEL"] == "gpt-4o"
        assert written["CUSTOM_LLM_MODEL"] == "gpt-4o"
        assert written["LLM_BASE_URL"] == "https://api.openai.com"

    async def test_llm_apply_platform_clears_default_model(self, client, monkeypatch):
        """Platform mode (no base_url) must NOT persist a local default model.

        The gateway assigns the default model remotely; stale LLM_MODEL and
        CUSTOM_LLM_MODEL values are cleared so a previous custom config cannot
        bleed into platform traffic.
        """
        writes: list[tuple[str, str]] = []

        def _capture(key, value, description=None):
            del description
            writes.append((key, value or ""))

        monkeypatch.setattr(
            "app.api.routes.system.SystemConfigService",
            SimpleNamespace(set_value=_capture),
        )
        monkeypatch.setattr(
            "app.api.routes.system.LLMFactory",
            SimpleNamespace(clear_cache=lambda: None),
        )
        resp = await client.post(
            "/system/llm/apply",
            json={
                "provider": "evocloud",
                "model": "gpt-4o",
                "base_url": None,
            },
        )
        assert resp.status_code == 200
        written = dict(writes)
        assert written["LLM_CONFIG_TYPE"] == "platform"
        assert written["LLM_MODEL"] == ""
        assert written["CUSTOM_LLM_MODEL"] == ""
        assert written["LLM_BASE_URL"] == ""

    async def test_llm_apply_custom_ignores_legacy_default_model_id(self, client, monkeypatch):
        """custom mode routes LLM_MODEL from req.model.

        The legacy default_model_id field was removed; a stale payload field is
        tolerated (extra=allow) but must not change what gets persisted."""
        writes: list[tuple[str, str]] = []

        def _capture(key, value, description=None):
            del description
            writes.append((key, value or ""))

        monkeypatch.setattr(
            "app.api.routes.system.SystemConfigService",
            SimpleNamespace(set_value=_capture),
        )
        monkeypatch.setattr(
            "app.api.routes.system.LLMFactory",
            SimpleNamespace(clear_cache=lambda: None),
        )
        resp = await client.post(
            "/system/llm/apply",
            json={
                "provider": "openai",
                "model": "gpt-4o",
                "default_model_id": "custom-openai-gpt-4o",
                "base_url": "https://api.openai.com",
            },
        )
        assert resp.status_code == 200
        written = dict(writes)
        assert written["LLM_CONFIG_TYPE"] == "custom"
        assert written["LLM_MODEL"] == "gpt-4o"
        assert written["CUSTOM_LLM_MODEL"] == "gpt-4o"

    async def test_llm_apply_custom_persists_vision_api_key_and_headers(
        self, client, monkeypatch
    ):
        """custom mode persists optional vision / api_key / headers keys."""
        writes: list[tuple[str, str]] = []

        def _capture(key, value, description=None):
            del description
            writes.append((key, value or ""))

        monkeypatch.setattr(
            "app.api.routes.system.SystemConfigService",
            SimpleNamespace(set_value=_capture),
        )
        monkeypatch.setattr(
            "app.api.routes.system.LLMFactory",
            SimpleNamespace(clear_cache=lambda: None),
        )
        resp = await client.post(
            "/system/llm/apply",
            json={
                "provider": "openai",
                "provider_type": "anthropic",
                "model": "claude-3-5-sonnet",
                "base_url": "https://api.anthropic.com",
                "api_key": "sk-anthropic",
                "vision_model": "gpt-4o",
                "vision_base_url": "https://api.openai.com/v1",
                "vision_api_key": "sk-vision",
                "vision_provider_type": "openai",
                "headers": {"X-Custom": "1", "Authorization": "Bearer tok"},
            },
        )
        assert resp.status_code == 200
        written = dict(writes)
        assert written["LLM_PROVIDER"] == "openai"
        assert written["LLM_PROVIDER_TYPE"] == "anthropic"
        assert written["LLM_API_KEY"] == "sk-anthropic"
        assert written["VISION_MODEL"] == "gpt-4o"
        assert written["VISION_BASE_URL"] == "https://api.openai.com/v1"
        assert written["VISION_API_KEY"] == "sk-vision"
        assert written["VISION_PROVIDER_TYPE"] == "openai"
        assert written["LLM_HEADERS"] == '{"X-Custom": "1", "Authorization": "Bearer tok"}'

    async def test_llm_apply_platform_clears_ignoring_legacy_default_model_id(
        self, client, monkeypatch
    ):
        """Platform mode must clear model keys even when a legacy
        default_model_id is supplied — the gateway owns default selection and
        stale ids must not be persisted (extra field is tolerated, not honored)."""
        writes: list[tuple[str, str]] = []

        def _capture(key, value, description=None):
            del description
            writes.append((key, value or ""))

        monkeypatch.setattr(
            "app.api.routes.system.SystemConfigService",
            SimpleNamespace(set_value=_capture),
        )
        monkeypatch.setattr(
            "app.api.routes.system.LLMFactory",
            SimpleNamespace(clear_cache=lambda: None),
        )
        resp = await client.post(
            "/system/llm/apply",
            json={
                "provider": "evocloud",
                "model": "gpt-4o",
                "default_model_id": "evocloud-deepseek-v4",
                "base_url": None,
            },
        )
        assert resp.status_code == 200
        written = dict(writes)
        assert written["LLM_CONFIG_TYPE"] == "platform"
        assert written["LLM_MODEL"] == ""
        assert written["CUSTOM_LLM_MODEL"] == ""
        assert written["LLM_BASE_URL"] == ""


# ---------------------------------------------------------------------------
# Cloud status
# ---------------------------------------------------------------------------


class TestCloudStatus:
    async def test_cloud_status(self, client, monkeypatch):
        fake_link = SimpleNamespace(
            device_key="dk-123",
            is_connected=lambda: True,
            device_name="MyDevice",
        )
        fake_api = SimpleNamespace(base_url="https://cloud.example.com")
        monkeypatch.setattr(
            "app.core.evocloud.evocloud_manager",
            SimpleNamespace(
                get_token=lambda: _async_return("tok-abc"),
                link=fake_link,
                api=fake_api,
            ),
        )
        resp = await client.get("/system/cloud-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_logged_in"] is True
        assert body["is_linked"] is True
        assert body["device_name"] == "MyDevice"

    async def test_cloud_status_not_logged_in(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.core.evocloud.evocloud_manager",
            SimpleNamespace(
                get_token=lambda: _async_return(None),
                link=None,
                api=None,
            ),
        )
        resp = await client.get("/system/cloud-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_logged_in"] is False
        assert body["is_linked"] is False


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _async_return(value):
    return value
