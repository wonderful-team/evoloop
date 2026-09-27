"""Unit tests for LLMPlatformService generation-model discovery.

Covers parsing of image/video model capabilities from the gateway model list
and the get_image_models/get_video_models accessors.
"""


import pytest

import app.infrastructure.llm.platform_service as ps


def _reset_cache():
    ps.llm_platform_service._models_cache.clear()
    ps.llm_platform_service._last_fetch_time = 0


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _reset_cache()


def _mock_gateway_models(monkeypatch, models):
    class _FakeAPI:
        def __init__(self):
            self.models = models

        async def get_llm_models(self):
            return {"code": 0, "data": {"models": self.models}}

    class _FakeManager:
        def __init__(self):
            self.api = _FakeAPI()

    monkeypatch.setattr(ps, "evocloud_manager", _FakeManager())


@pytest.mark.asyncio
async def test_fetch_parses_image_and_video_capabilities(monkeypatch):
    _mock_gateway_models(monkeypatch, [
        {
            "model_id": "gpt-4o",
            "display_name": "GPT-4o",
            "provider_name": "openai",
            "model_type": "llm",
            "config_type": "evoloop",
            "supports_image_generation": False,
            "supports_video_generation": False,
        },
        {
            "model_id": "gpt-image-1",
            "display_name": "GPT Image 1",
            "provider_name": "openai",
            "model_type": "image",
            "config_type": "evoloop",
            "supports_image_generation": True,
            "supports_video_generation": False,
        },
        {
            "model_id": "gpt-video-1",
            "display_name": "GPT Video 1",
            "provider_name": "openai",
            "model_type": "video",
            "config_type": "evoloop",
            "supports_image_generation": False,
            "supports_video_generation": True,
        },
    ])

    await ps.llm_platform_service.fetch_platform_models(force_refresh=True)

    image = ps.llm_platform_service.get_model_by_id("gpt-image-1")
    video = ps.llm_platform_service.get_model_by_id("gpt-video-1")
    chat = ps.llm_platform_service.get_model_by_id("gpt-4o")

    assert image is not None
    assert image.model_type == "image"
    assert image.supports_image_generation is True
    assert image.supports_video_generation is False

    assert video is not None
    assert video.model_type == "video"
    assert video.supports_video_generation is True

    assert chat is not None
    assert chat.supports_image_generation is False


@pytest.mark.asyncio
async def test_get_image_models_filters(monkeypatch):
    _mock_gateway_models(monkeypatch, [
        {"model_id": "a", "model_type": "llm", "provider_name": "o", "config_type": "evoloop"},
        {"model_id": "b", "model_type": "image", "provider_name": "o", "config_type": "evoloop"},
        {"model_id": "c", "model_type": "llm", "provider_name": "o", "config_type": "evoloop",
         "supports_image_generation": True},
    ])

    await ps.llm_platform_service.fetch_platform_models(force_refresh=True)
    image_models = ps.llm_platform_service.get_image_models()
    ids = {m.model_id for m in image_models}
    assert "b" in ids
    assert "c" in ids
    assert "a" not in ids


@pytest.mark.asyncio
async def test_get_video_models_filters(monkeypatch):
    _mock_gateway_models(monkeypatch, [
        {"model_id": "a", "model_type": "video", "provider_name": "o", "config_type": "evoloop"},
        {"model_id": "b", "model_type": "llm", "provider_name": "o", "config_type": "evoloop",
         "supports_video_generation": True},
        {"model_id": "c", "model_type": "llm", "provider_name": "o", "config_type": "evoloop"},
    ])

    await ps.llm_platform_service.fetch_platform_models(force_refresh=True)
    video_models = ps.llm_platform_service.get_video_models()
    ids = {m.model_id for m in video_models}
    assert "a" in ids
    assert "b" in ids
    assert "c" not in ids
