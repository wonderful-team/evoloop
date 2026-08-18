"""
VideoService — high-level API for video processing.

Combines FrameExtractor + FrameCompressor for use by ReferenceService
and other consumers that need to extract frames from videos.

Usage:
    from app.infrastructure.video.service import VideoService

    frames = await VideoService.extract_keyframes("https://.../video.mp4", count=5)
    info = await VideoService.get_metadata("https://.../video.mp4")
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import httpx

from app.infrastructure.video.compressor import FrameCompressor
from app.infrastructure.video.extractor import FrameExtractor
from app.infrastructure.video.schemas import CompressedFrame, VideoInfo

logger = logging.getLogger(__name__)


class VideoService:
    """Generic video processing service for the message pipeline."""

    # OpenAI-compatible image format for extracted frames
    EXTRACTED_FORMAT = "JPEG"
    EXTRACTED_QUALITY = 85
    DEFAULT_MAX_WIDTH = 1024

    @staticmethod
    async def get_metadata(video_url_or_path: str) -> VideoInfo:
        """Get video metadata (duration, resolution, fps)."""
        local_path = await VideoService._ensure_local(video_url_or_path)
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate,duration",
                "-show_entries", "format=duration",
                "-of", "json",
                local_path,
            ]
            result = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, _ = await result.communicate()

            data = json.loads(stdout.decode())
            stream = data["streams"][0]
            fmt = data.get("format", {})
            duration = float(fmt.get("duration") or stream.get("duration", 0.0))
            width = int(stream["width"])
            height = int(stream["height"])
            fps_str = stream.get("r_frame_rate", "15/1")
            fps = float(fps_str.split("/")[0]) / float(fps_str.split("/")[1]) if "/" in fps_str else float(fps_str)
            return VideoInfo(duration=duration, width=width, height=height, fps=fps, path=local_path)
        except Exception as e:
            logger.exception(f"[VideoService] Failed to get metadata for {video_url_or_path}: {e}")
            return VideoInfo(duration=0.0, width=0, height=0, fps=0.0, path=local_path)

    @staticmethod
    async def extract_keyframes(
        video_url_or_path: str,
        count: int = 5,
        max_width: int | None = None,
    ) -> list[CompressedFrame]:
        """
        Extract evenly-spaced keyframes from a video and return compressed frames.

        Args:
            video_url_or_path: URL or local path to the video.
            count: Number of keyframes to extract (evenly spaced).
            max_width: Max width for compression (default 1024).

        Returns:
            List of CompressedFrame objects with compressed image data.
        """
        local_path = await VideoService._ensure_local(video_url_or_path)
        info = await VideoService.get_metadata(local_path)
        if info.duration <= 0 or count <= 0:
            return []

        # Compute evenly-spaced timestamps
        interval = info.duration / (count + 1)
        timestamps_ms = [int(interval * (i + 1) * 1000) for i in range(count)]

        # Extract frames
        extractor = FrameExtractor(local_path)
        frame_paths = await asyncio.get_running_loop().run_in_executor(
            None, extractor.extract_frames, timestamps_ms
        )

        # Compress frames
        compressor = FrameCompressor()
        result: list[CompressedFrame] = []
        width = max_width or VideoService.DEFAULT_MAX_WIDTH
        for frame_path in frame_paths:
            try:
                compressed = compressor.compress(frame_path)
                result.append(compressed)
            except Exception as e:
                logger.warning(f"[VideoService] Failed to compress frame {frame_path}: {e}", exc_info=True)
                continue

        return result

    @staticmethod
    async def _ensure_local(video_url_or_path: str) -> str:
        """If the input is a URL, download it to a temp file. Otherwise return as-is."""
        if video_url_or_path.startswith(("http://", "https://")):
            suffix = Path(video_url_or_path).suffix or ".mp4"
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp_path = tmp.name
            tmp.close()
            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream("GET", video_url_or_path) as resp:
                        resp.raise_for_status()
                        with open(tmp_path, "wb") as f:
                            async for chunk in resp.aiter_bytes():
                                f.write(chunk)
                logger.debug(f"[VideoService] Downloaded {video_url_or_path} -> {tmp_path}")
                return tmp_path
            except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise RuntimeError(f"Failed to download video {video_url_or_path}: {e}")
        return video_url_or_path
