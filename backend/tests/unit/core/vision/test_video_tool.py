"""Unit tests for the ``video`` facade tool (analyze + generate).

Covers:
1. Validation branches (missing source / missing prompt).
2. Analyze happy-path with mocked VideoService + VisionEngine.
3. Analyze failure branches (no frames / vision produced no summary).
4. Generate happy-path (text-to-video & image-to-video) with mocked OpenAI SDK,
   gateway, path resolution and download.
5. Gateway-not-configured error branch.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.vision.tools import video as video_tool


class TestValidation:
    @pytest.mark.asyncio
    async def test_analyze_requires_source(self):
        text = await video_tool._analyze(None)
        assert "requires `source`" in text

    @pytest.mark.asyncio
    async def test_generate_requires_prompt(self):
        text = await video_tool._generate(None)
        assert "requires `prompt`" in text


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_happy_path(self, monkeypatch):
        frame = SimpleNamespace(data=b"\xff\xd8\xff\xe0fakejpeg")
        processed = {"calls": 0}

        async def _fake_extract(source, count):
            assert source == "/tmp/clip.mp4"
            assert count == 4
            return [frame]

        async def _fake_process(task, image_source, prompt, **kwargs):  # noqa: ARG001
            processed["calls"] += 1
            assert task.value == "analyze"
            return SimpleNamespace(success=True, summary="waves crashing")

        monkeypatch.setattr(
            "app.infrastructure.vision.video.service.VideoService.extract_keyframes",
            _fake_extract,
        )
        monkeypatch.setattr(
            "app.core.vision.engine.vision_engine.process",
            _fake_process,
        )
        text = await video_tool._analyze("/tmp/clip.mp4", "What happens?")
        assert "Frame 1: waves crashing" in text
        assert processed["calls"] == 1

    @pytest.mark.asyncio
    async def test_analyze_no_frames(self, monkeypatch):
        async def _fake_extract(source, count):  # noqa: ARG001
            return []

        monkeypatch.setattr(
            "app.infrastructure.vision.video.service.VideoService.extract_keyframes",
            _fake_extract,
        )
        text = await video_tool._analyze("/tmp/clip.mp4")
        assert "any frames" in text

    @pytest.mark.asyncio
    async def test_analyze_no_summary(self, monkeypatch):
        frame = SimpleNamespace(data=b"fake")

        async def _fake_extract(source, count):  # noqa: ARG001
            return [frame]

        async def _fake_process(task, image_source, prompt, **kwargs):  # noqa: ARG001
            return SimpleNamespace(success=False, metadata={"error": "vlm down"})

        monkeypatch.setattr(
            "app.infrastructure.vision.video.service.VideoService.extract_keyframes",
            _fake_extract,
        )
        monkeypatch.setattr(
            "app.core.vision.engine.vision_engine.process",
            _fake_process,
        )
        text = await video_tool._analyze("/tmp/clip.mp4")
        assert "no summary" in text


class TestGenerate:
    """video generate：httpx JSON 直调网关（openai SDK 的 multipart 协议
    与网关 Go JSON schema 不兼容，实现已改为 httpx 直调）。"""

    def _mock_gateway(self, monkeypatch, *, final_status: str = "completed"):
        """注入 MockTransport 工厂，返回 (created_payloads, poll_count_holder)。"""

        created: list[dict] = []
        poll_counter = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if request.method == "POST" and path.endswith("/videos"):
                created.append(json.loads(request.read()))
                return httpx.Response(200, json={"id": "video_123", "status": "queued"})
            if request.method == "GET" and path.endswith("/videos/video_123/content"):
                return httpx.Response(200, content=b"fake-video-bytes")
            if request.method == "GET" and path.endswith("/videos/video_123"):
                poll_counter["n"] += 1
                return httpx.Response(
                    200, json={"id": "video_123", "status": final_status, "error": None}
                )
            return httpx.Response(404, json={"error": {"message": "not found"}})

        transport = httpx.MockTransport(handler)
        real_cls = httpx.AsyncClient

        def fake_client(**kwargs):
            return real_cls(transport=transport, **kwargs)

        monkeypatch.setattr(
            "app.core.vision.tools.video._new_http_client",
            lambda: fake_client(timeout=60.0),
        )
        return created, poll_counter

    async def _run(self, monkeypatch, *, final_status: str = "completed", **kwargs):
        created, polls = self._mock_gateway(monkeypatch, final_status=final_status)

        self.removed = []
        self.upload_calls = []

        async def _fake_write_temp(data, suffix):  # noqa: ARG001
            return f"/tmp/fake_media{suffix}"

        async def _fake_upload(file_path, kind):
            self.upload_calls.append((file_path, kind))
            return "https://cloud.example.com/upload/chat_video/x.mp4"

        async def _fake_remove(path):
            self.removed.append(path)

        import app.core.evocloud as evo_pkg

        monkeypatch.setattr(
            evo_pkg, "evocloud_manager",
            SimpleNamespace(
                get_token=AsyncMock(return_value="tok"),
                api=SimpleNamespace(
                    root_url="https://gw.example.com",
                    upload_chat_media=_fake_upload,
                ),
            ),
        )
        monkeypatch.setattr(
            "app.core.vision.tools.video.remove_file", _fake_remove
        )

        text = await video_tool._generate(**kwargs)
        return text, created, polls

    @pytest.mark.asyncio
    async def test_generate_text_to_video(self, monkeypatch):
        from app.core.context.manager import ContextManager, EvoContext

        with ContextManager.use(EvoContext()):
            text, created, _ = await self._run(
                monkeypatch,
                prompt="ocean waves",
            )
            assert text.startswith(
                "[Video: generated video](https://cloud.example.com/upload/chat_video/x.mp4)"
            )
            assert len(created) == 1
            assert created[0]["prompt"] == "ocean waves"
            # 网关 seconds 是 int（协议修复回归断言）
            assert created[0]["seconds"] == 5
            assert "input_reference" not in created[0]
            assert [c[1] for c in self.upload_calls] == ["video"]
            ctx = ContextManager.current()
            pending = getattr(ctx.metadata, "pending_media_refs", None) or []
            assert pending[0]["type"] == "video"
            assert (
                pending[0]["target_id"]
                == "https://cloud.example.com/upload/chat_video/x.mp4"
            )

    @pytest.mark.asyncio
    async def test_generate_image_to_video(self, monkeypatch):
        from app.core.context.manager import ContextManager, EvoContext

        source = "/tmp/fake_ref.png"

        async def _fake_load_bytes(source_path, config):  # noqa: ARG001
            return b"ref-bytes"

        monkeypatch.setattr(
            "app.core.vision.tools.video.load_source_bytes", _fake_load_bytes
        )
        with ContextManager.use(EvoContext()):
            text, created, _ = await self._run(
                monkeypatch,
                prompt="ocean waves",
                source=source,
            )
            assert text.startswith("[Video: generated video]")
            assert created[0].get("input_reference") == (
                "https://cloud.example.com/upload/chat_video/x.mp4"
            )

    @pytest.mark.asyncio
    async def test_generate_not_completed(self, monkeypatch):
        from app.core.context.manager import ContextManager, EvoContext

        with ContextManager.use(EvoContext()):
            text, _, _ = await self._run(
                monkeypatch, prompt="x", final_status="failed"
            )
            assert "did not complete" in text
            assert "status=failed" in text

    @pytest.mark.asyncio
    async def test_generate_gateway_not_configured(self, monkeypatch):
        import app.core.evocloud as evo_pkg

        monkeypatch.setattr(
            evo_pkg, "evocloud_manager",
            SimpleNamespace(get_token=AsyncMock(return_value="tok"), api=None),
        )
        text = await video_tool._generate("x")
        assert "video generation failed" in text
