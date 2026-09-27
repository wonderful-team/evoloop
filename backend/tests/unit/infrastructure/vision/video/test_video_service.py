"""Unit tests for VideoService (app/infrastructure/vision/video/service.py).

Covers the keyframe-extraction orchestration used on the user path
(user uploads a video → extract_keyframes → frames for vision).
External deps (ffprobe, ffmpeg, FrameExtractor, FrameCompressor) are mocked.
"""

from types import SimpleNamespace

import pytest

from app.infrastructure.vision.video.service import VideoService


class TestGetMetadata:
    @pytest.mark.asyncio
    async def test_returns_video_info(self, monkeypatch):
        info = SimpleNamespace(
            duration=10.0, width=1920, height=1080, fps=30.0, path="/v.mp4"
        )

        async def _fake_get_metadata(path):  # noqa: ARG001
            return info

        async def _fake_ensure_local(path):  # noqa: ARG001
            return "/v.mp4"

        monkeypatch.setattr(VideoService, "_ensure_local", _fake_ensure_local)
        monkeypatch.setattr(VideoService, "get_metadata", _fake_get_metadata)
        result = await VideoService.get_metadata("https://x/v.mp4")
        assert result.duration == 10.0
        assert result.width == 1920


class TestExtractKeyframes:
    @pytest.mark.asyncio
    async def test_returns_empty_when_zero_duration(self, monkeypatch):
        info = SimpleNamespace(duration=0.0, width=0, height=0, fps=0.0, path="/v.mp4")

        async def _fake_get_metadata(path):  # noqa: ARG001
            return info

        async def _fake_ensure_local(path):
            return path

        monkeypatch.setattr(VideoService, "_ensure_local", _fake_ensure_local)
        monkeypatch.setattr(VideoService, "get_metadata", _fake_get_metadata)
        frames = await VideoService.extract_keyframes("/v.mp4", count=5)
        assert frames == []

    @pytest.mark.asyncio
    async def test_extracts_and_compresses_frames(self, monkeypatch):
        info = SimpleNamespace(
            duration=10.0, width=1920, height=1080, fps=30.0, path="/v.mp4"
        )

        async def _fake_ensure_local(path):  # noqa: ARG001
            return "/v.mp4"

        async def _fake_get_metadata(path):  # noqa: ARG001
            return info

        monkeypatch.setattr(VideoService, "_ensure_local", _fake_ensure_local)
        monkeypatch.setattr(VideoService, "get_metadata", _fake_get_metadata)

        # FrameExtractor stub
        class _FakeExtractor:
            def __init__(self, path):
                self.path = path

            def extract_frames(self, timestamps_ms):
                return [f"/tmp/frame_{t}.jpg" for t in timestamps_ms]

        # FrameCompressor stub
        class _FakeCompressor:
            def __init__(self):
                self.calls = []

            def compress(self, frame_path):
                self.calls.append(frame_path)
                return SimpleNamespace(
                    data=b"jpegdata", width=640, height=360,
                    original_size=(1920, 1080), timestamp=0.0,
                )

        import app.infrastructure.vision.video.service as svc

        monkeypatch.setattr(svc, "FrameExtractor", _FakeExtractor)
        monkeypatch.setattr(svc, "FrameCompressor", _FakeCompressor)

        frames = await VideoService.extract_keyframes("/v.mp4", count=4)
        assert len(frames) == 4
        assert frames[0].data == b"jpegdata"
        assert frames[0].width == 640

    @pytest.mark.asyncio
    async def test_skips_frames_that_fail_compression(self, monkeypatch):
        info = SimpleNamespace(
            duration=10.0, width=1920, height=1080, fps=30.0, path="/v.mp4"
        )

        async def _fake_ensure_local(path):  # noqa: ARG001
            return "/v.mp4"

        async def _fake_get_metadata(path):  # noqa: ARG001
            return info

        monkeypatch.setattr(VideoService, "_ensure_local", _fake_ensure_local)
        monkeypatch.setattr(VideoService, "get_metadata", _fake_get_metadata)

        class _FakeExtractor:
            def __init__(self, path):
                pass

            def extract_frames(self, timestamps_ms):
                return [f"/tmp/f{i}.jpg" for i in range(len(timestamps_ms))]

        class _FakeCompressor:
            def __init__(self):
                self.calls = 0

            def compress(self, frame_path):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("bad frame")
                return SimpleNamespace(
                    data=b"jpeg", width=10, height=10,
                    original_size=(10, 10), timestamp=0.0,
                )

        import app.infrastructure.vision.video.service as svc

        monkeypatch.setattr(svc, "FrameExtractor", _FakeExtractor)
        monkeypatch.setattr(svc, "FrameCompressor", _FakeCompressor)

        frames = await VideoService.extract_keyframes("/v.mp4", count=3)
        # 第一帧压缩失败被跳过，剩余 2 帧
        assert len(frames) == 2

    @pytest.mark.asyncio
    async def test_ensure_local_passthrough_for_local_path(self, monkeypatch):
        result = await VideoService._ensure_local("/local/video.mp4")
        assert result == "/local/video.mp4"
