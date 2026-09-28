"""Unit tests for the ``image`` facade tool (analyze + generate).

Covers:
1. Facade dispatch (action=analyze / action=generate).
2. Validation branches (missing source / missing prompt).
3. Analyze happy-path via mocked VisionEngine.
4. Generate happy-path (text-to-image & image-to-image) with mocked OpenAI SDK,
   gateway, path resolution and download.
5. Gateway-not-configured error branch.
"""

from types import SimpleNamespace

import pytest

from app.core.vision.tools import image as image_tool


class TestValidation:
    @pytest.mark.asyncio
    async def test_analyze_requires_source(self):
        text = await image_tool._analyze(None)
        assert "requires `source`" in text

    @pytest.mark.asyncio
    async def test_generate_requires_prompt(self):
        text = await image_tool._generate(None)
        assert "requires `prompt`" in text


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_happy_path(self, monkeypatch, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake")
        result = SimpleNamespace(success=True, summary="A red apple on a table.")
        processed = {"called": 0}

        async def _fake_process(task, image_source, prompt, **kwargs):  # noqa: ARG001
            processed["called"] += 1
            assert task.value == "analyze"
            assert image_source == str(img)
            return result

        monkeypatch.setattr(image_tool.vision_engine, "process", _fake_process)
        text = await image_tool._analyze(str(img), "What is this?")
        assert text == "A red apple on a table."
        assert processed["called"] == 1

    @pytest.mark.asyncio
    async def test_analyze_resolves_uploads_relative_path(self, monkeypatch, tmp_path):
        img = tmp_path / "ref.jpg"
        img.write_bytes(b"fake")
        processed = {"source": None}

        async def _fake_process(task, image_source, prompt, **kwargs):  # noqa: ARG001
            processed["source"] = image_source
            return SimpleNamespace(success=True, summary="ok")

        monkeypatch.setattr(image_tool.vision_engine, "process", _fake_process)

        import app.core.vision.tools._media as media

        async def _fake_resolve(source, config=None):  # noqa: ARG001
            return str(img)

        monkeypatch.setattr(media, "resolve_media_source", _fake_resolve)

        text = await image_tool._analyze("uploads/ref.jpg")
        assert text == "ok"
        assert processed["source"] == str(img)

    @pytest.mark.asyncio
    async def test_analyze_unresolvable_source_returns_error(self, monkeypatch, tmp_path):
        import app.core.vision.tools._media as media

        async def _fake_resolve(source, config=None):  # noqa: ARG001
            raise FileNotFoundError(f"upload file not found: {source}")

        monkeypatch.setattr(media, "resolve_media_source", _fake_resolve)

        text = await image_tool._analyze("uploads/ghost.jpg")
        assert text.startswith("Error: cannot resolve image source")

    @pytest.mark.asyncio
    async def test_analyze_failure_returns_error(self, monkeypatch, tmp_path):
        img = tmp_path / "x.png"
        img.write_bytes(b"fake")
        result = SimpleNamespace(success=False, metadata={"error": "boom"})

        async def _fake_process(task, image_source, prompt, **kwargs):  # noqa: ARG001
            return result

        monkeypatch.setattr(image_tool.vision_engine, "process", _fake_process)
        text = await image_tool._analyze(str(img))
        assert text.startswith("Error:")
        assert "boom" in text

    @pytest.mark.asyncio
    async def test_analyze_empty_summary_uses_fallback(self, monkeypatch, tmp_path):
        img = tmp_path / "x.png"
        img.write_bytes(b"fake")
        result = SimpleNamespace(success=True, summary=None)

        async def _fake_process(task, image_source, prompt, **kwargs):  # noqa: ARG001
            return result

        monkeypatch.setattr(image_tool.vision_engine, "process", _fake_process)
        text = await image_tool._analyze(str(img))
        assert text == "Image analysis completed."


class TestGenerate:
    def _mock_client(self, monkeypatch):
        """Return a fake OpenAI client and patch create_generation_client."""

        class FakeImageData:
            url = "https://gw.example.com/generated.png"

        class FakeImagesResponse:
            data = [FakeImageData()]

        class FakeImages:
            def __init__(self):
                self.generated = []
                self.edited = []

            async def generate(self, **kwargs):
                self.generated.append(kwargs)
                return FakeImagesResponse()

            async def edit(self, **kwargs):
                self.edited.append(kwargs)
                return FakeImagesResponse()

        class FakeClient:
            last_instance = None

            def __init__(self, **kwargs):
                self.created_kwargs = kwargs
                self.images = FakeImages()
                FakeClient.last_instance = self

        monkeypatch.setattr(
            "app.infrastructure.vision.generation.create_generation_client",
            FakeClient,
        )
        return FakeClient

    async def _run(self, monkeypatch, **kwargs):
        fake_client_cls = self._mock_client(monkeypatch)

        # 新契约：下载字节 → 写临时文件 → 上传 MC 换公网 URL → 删临时文件
        self.removed = []
        self.upload_calls = []

        async def _fake_download_bytes(url):
            assert url == "https://gw.example.com/generated.png"
            return b"generated-png-bytes"

        async def _fake_write_temp(data, suffix):  # noqa: ARG001
            return f"/tmp/fake_media{suffix}"

        async def _fake_upload(file_path, kind):
            self.upload_calls.append((file_path, kind))
            return "https://cloud.example.com/upload/chat_img/x.png"

        async def _fake_remove(path):
            self.removed.append(path)

        monkeypatch.setattr(
            "app.core.vision.tools.image.download_bytes", _fake_download_bytes
        )
        monkeypatch.setattr(
            "app.core.vision.tools.image.write_temp", _fake_write_temp
        )
        import app.core.evocloud as evo_pkg

        monkeypatch.setattr(
            evo_pkg, "evocloud_manager",
            SimpleNamespace(api=SimpleNamespace(upload_chat_media=_fake_upload)),
        )
        monkeypatch.setattr(
            "app.core.vision.tools.image.remove_file", _fake_remove
        )

        text = await image_tool._generate(**kwargs)
        client = fake_client_cls.last_instance
        return text, client

    @pytest.mark.asyncio
    async def test_generate_text_to_image(self, monkeypatch):
        text, client = await self._run(
            monkeypatch,
            prompt="a cat",
        )
        # 返回公网 URL 的 markdown 图片链接
        assert text.startswith(
            "![generated image](https://cloud.example.com/upload/chat_img/x.png)"
        )
        assert len(client.images.generated) == 1
        assert client.images.generated[0]["prompt"] == "a cat"
        assert client.images.generated[0]["size"] == "1024x1024"

    @pytest.mark.asyncio
    async def test_generate_stashes_structured_reference(self, monkeypatch):
        """工具应把结构化媒体引用暂存到执行上下文（不依赖模型复述链接）。"""
        from app.core.context.manager import ContextManager, EvoContext

        with ContextManager.use(EvoContext()):
            await self._run(monkeypatch, prompt="a cat")
            ctx = ContextManager.current()
            pending = getattr(ctx.metadata, "pending_media_refs", None) or []
            assert len(pending) == 1
            assert pending[0]["type"] == "image"
            assert (
                pending[0]["target_id"]
                == "https://cloud.example.com/upload/chat_img/x.png"
            )

    @pytest.mark.asyncio
    async def test_generate_cleans_up_temp_file(self, monkeypatch):
        await self._run(monkeypatch, prompt="a cat")
        assert self.removed == ["/tmp/fake_media.png"]

    @pytest.mark.asyncio
    async def test_generate_image_to_image_uses_reference_url(self, monkeypatch):
        """图生图：本地参考图先上传 MC 换 URL，再以 extra_body.image 传给网关。"""
        from app.core.context.manager import ContextManager, EvoContext

        async def _fake_load_bytes(source, config=None):  # noqa: ARG001
            return b"fake-png-bytes"

        monkeypatch.setattr(
            "app.core.vision.tools.image.load_source_bytes", _fake_load_bytes
        )

        with ContextManager.use(EvoContext()):
            text, client = await self._run(
                monkeypatch,
                prompt="make it a dog",
                source="/tmp/ref.png",
            )
            assert text.startswith(
                "![generated image](https://cloud.example.com/upload/chat_img/x.png)"
            )
            # 上传两次：先参考图、后生成产物（均换公网 URL）
            assert self.upload_calls == [
                ("/tmp/fake_media.png", "image"),
                ("/tmp/fake_media.png", "image"),
            ]
            # 以 extra_body.image（公网 URL）传给网关，而非 multipart edit
            assert client.images.generated[0]["extra_body"]["image"] == [
                "https://cloud.example.com/upload/chat_img/x.png"
            ]
            # 清理 stash
            ctx = ContextManager.current()
            ctx.metadata.pending_media_refs = []

    @pytest.mark.asyncio
    async def test_generate_gateway_not_configured(self, monkeypatch):
        def _raise():
            raise ValueError("EvoLoop Gateway URL not configured")

        monkeypatch.setattr(
            "app.infrastructure.vision.generation.create_generation_client",
            _raise,
        )
        text = await image_tool._generate("x")
        assert "Gateway URL not configured" in text

    @pytest.mark.asyncio
    async def test_generate_no_data_returns_error(self, monkeypatch):
        class FakeImagesResponse:
            data = []

        class FakeImages:
            async def generate(self, **kwargs):
                return FakeImagesResponse()

        class FakeClient:
            def __init__(self, **kwargs):
                self.images = FakeImages()

        monkeypatch.setattr(
            "app.infrastructure.vision.generation.create_generation_client",
            FakeClient,
        )
        text = await image_tool._generate("x")
        assert "no result" in text
