"""
Frame Extractor — generic video keyframe extraction via ffmpeg.

Extracts frames at specific timestamps and optionally analyzes them with Vision/OCR.
Migrated from app.core.learning.frame_extractor.
"""

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
                , exc_info=True)
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
                logger.exception(f"ffmpeg timed out extracting frame at {ts_sec}s")
            except FileNotFoundError:
                logger.error("ffmpeg not found. Install it with: brew install ffmpeg")
                break
        return extracted_paths
