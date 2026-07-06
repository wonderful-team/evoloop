"""
Frame Extractor — generic video keyframe extraction via ffmpeg.

Extracts frames at specific timestamps and optionally analyzes them with Vision/OCR.
Migrated from app.core.learning.frame_extractor.
"""

import asyncio
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class FrameExtractor:
    """Extracts keyframes from a video file using ffmpeg."""

    def __init__(self, video_path: str, session_id: str | None = None):
        self.video_path = video_path
        self.session_id = session_id
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

    def _get_output_dir(self, session_id: str | None = None) -> Path:
        if session_id:
            try:
                from app.infrastructure.vision.storage import screen_recording_storage

                return Path(screen_recording_storage.get_frames_dir(session_id))
            except (ImportError, OSError, ValueError, RuntimeError) as e:
                logger.warning(
                    f"[FrameExtractor] Failed to use hierarchical storage: {e}, using fallback"
                )
        video_name = Path(self.video_path).stem
        output_dir = Path(self.video_path).parent / f"{video_name}_frames"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def extract_frames(self, timestamps_ms: list[int]) -> list[str]:
        output_dir = self._get_output_dir(self.session_id)
        extracted_paths = []
        for ts_ms in timestamps_ms:
            ts_sec = ts_ms / 1000.0
            output_path = output_dir / f"frame_{ts_ms}.png"
            if output_path.exists():
                extracted_paths.append(str(output_path))
                continue
            try:
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-ss",
                        f"{ts_sec:.3f}",
                        "-i",
                        self.video_path,
                        "-frames:v",
                        "1",
                        "-q:v",
                        "2",
                        "-pix_fmt",
                        "yuvj420p",
                        "-y",
                        str(output_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and output_path.exists():
                    extracted_paths.append(str(output_path))
                else:
                    logger.warning(
                        f"Failed to extract frame at {ts_sec}s: {result.stderr[:200]}"
                    )
            except subprocess.TimeoutExpired:
                logger.error(f"ffmpeg timed out extracting frame at {ts_sec}s")
            except FileNotFoundError:
                logger.error("ffmpeg not found. Install it with: brew install ffmpeg")
                break
        return extracted_paths

    async def extract_and_analyze(
        self, timestamps_ms: list[int], on_android: bool = False
    ) -> list[dict]:
        loop = asyncio.get_running_loop()
        frame_paths = await loop.run_in_executor(
            None, self.extract_frames, timestamps_ms
        )
        results = []
        for ts_ms, frame_path in zip(timestamps_ms, frame_paths, strict=False):
            result = {
                "timestamp_ms": ts_ms,
                "screenshot_path": frame_path,
                "ocr_elements": [],
            }
            try:
                from app.infrastructure.vision.engine import vision_engine
                from app.infrastructure.vision.types import VisionTask

                vision_result = await vision_engine.process(
                    task=VisionTask.OCR, image_source=frame_path, on_android=on_android
                )
                if vision_result.success:
                    result["ocr_elements"] = [
                        {
                            "text": el.text,
                            "bounds": [
                                el.x - el.width // 2,
                                el.y - el.height // 2,
                                el.width,
                                el.height,
                            ],
                            "center": [el.x, el.y],
                        }
                        for el in vision_result.elements
                    ]
            except (OSError, RuntimeError, ValueError, TypeError) as e:
                logger.warning(f"Vision analysis skipped for {frame_path}: {e}")
            results.append(result)
        return results

    async def extract_single_frame(self, timestamp_sec: float) -> str:
        output_path = (
            self._get_output_dir(self.session_id)
            / f"frame_{int(timestamp_sec * 1000)}.jpg"
        )
        if output_path.exists():
            return str(output_path)
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{timestamp_sec:.3f}",
                    "-i",
                    self.video_path,
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    "-pix_fmt",
                    "yuvj420p",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and output_path.exists():
                return str(output_path)
            raise RuntimeError(f"ffmpeg failed: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"ffmpeg timed out extracting frame at {timestamp_sec}s")
        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found. Install it with: brew install ffmpeg")
