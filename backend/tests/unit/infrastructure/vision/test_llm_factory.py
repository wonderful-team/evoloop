"""Unit tests for VisionLLMFactory (app/infrastructure/vision/llm.py).

Covers the user-facing image-message construction helpers and the async
client factory, using a real temp image file for encoding paths.
"""

from types import SimpleNamespace

import pytest

from app.infrastructure.vision.llm import (
    VisionLLMFactory,
    get_vision_llm_async,
)


class TestImageMessage:
    def test_http_url_used_directly(self):
        msg = VisionLLMFactory.create_image_message(
            "https://example.com/pic.png", "what is this?"
        )
        parts = msg.content
        assert parts[0]["type"] == "image_url"
        assert parts[0]["image_url"]["url"] == "https://example.com/pic.png"
        assert parts[1]["type"] == "text"
        assert parts[1]["text"] == "what is this?"

    def test_local_file_encoded_as_data_url(self, tmp_path):
        p = tmp_path / "pic.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\nfakepngbytes")
        msg = VisionLLMFactory.create_image_message(str(p))
        url = msg.content[0]["image_url"]["url"]
        assert url.startswith("data:image/png;base64,")

    def test_unknown_ext_defaults_png(self, tmp_path):
        p = tmp_path / "pic.weird"
        p.write_bytes(b"data")
        msg = VisionLLMFactory.create_image_message(str(p))
        url = msg.content[0]["image_url"]["url"]
        assert url.startswith("data:image/png;base64,")



class TestClientFactory:
    @pytest.mark.asyncio
    async def test_create_vision_llm_async_uses_factory(self, monkeypatch):
        from app.infrastructure.llm import factory as factory_mod

        created = {"config": None}

        async def _fake_create_llm(config):
            created["config"] = config
            return SimpleNamespace(model="fake-vision")

        monkeypatch.setattr(factory_mod.LLMFactory, "create_llm", _fake_create_llm)

        llm = await VisionLLMFactory.create_vision_llm_async(
            model_name="gpt-vision-test"
        )
        assert llm.model == "fake-vision"
        assert created["config"].model_name == "gpt-vision-test"

    @pytest.mark.asyncio
    async def test_get_vision_llm_async_convenience(self, monkeypatch):
        from app.infrastructure.llm import factory as factory_mod

        async def _fake_create_llm(config):  # noqa: ARG001
            return SimpleNamespace(model="convenience")

        monkeypatch.setattr(factory_mod.LLMFactory, "create_llm", _fake_create_llm)

        llm = await get_vision_llm_async(model_name="some-vision")
        assert llm.model == "convenience"

    @pytest.mark.asyncio
    async def test_uses_configured_vision_model_when_no_arg(self, monkeypatch):
        from app.infrastructure.config import service as cfg_service
        from app.infrastructure.llm import factory as factory_mod

        captured = {}

        async def _fake_create_llm(config):
            captured["model"] = config.model_name
            return SimpleNamespace(model="ok")

        monkeypatch.setattr(factory_mod.LLMFactory, "create_llm", _fake_create_llm)
        monkeypatch.setattr(
            cfg_service.SystemConfigService, "get_value",
            lambda key, default=None: "vision-db-model"
            if key == "VISION_MODEL"
            else default,
        )

        await VisionLLMFactory.create_vision_llm_async()
        assert captured["model"] == "vision-db-model"


class TestMediaType:
    def test_media_type_by_ext(self):
        assert (
            VisionLLMFactory.get_image_media_type("x.png") == "image/png"
        )
        assert (
            VisionLLMFactory.get_image_media_type("x.jpeg") == "image/jpeg"
        )
        assert (
            VisionLLMFactory.get_image_media_type("x.webp") == "image/webp"
        )
        assert (
            VisionLLMFactory.get_image_media_type("x.unknown") == "image/png"
        )
