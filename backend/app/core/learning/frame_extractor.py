"""
Frame Extractor for Two-Track Recording Architecture.

Extracts keyframes from screen recording videos at specific timestamps
and optionally analyzes them with Vision/OCR.

Dependencies: System `ffmpeg` CLI (no Python packages required).
"""

import asyncio
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class FrameExtractor:
    """Extracts keyframes from a recorded video file using ffmpeg."""

    def __init__(self, video_path: str):
        """
        Args:
            video_path: Absolute path to the .mov/.mp4 video file.
        """
        self.video_path = video_path
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

    def _get_output_dir(self) -> Path:
        """Create and return the output directory for extracted frames."""
        video_name = Path(self.video_path).stem
        output_dir = Path(self.video_path).parent / f"{video_name}_frames"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def extract_frames(self, timestamps_ms: list[int]) -> list[str]:
        """
        Extract frames at given timestamps from the video.

        Args:
            timestamps_ms: List of timestamps in milliseconds.

        Returns:
            List of absolute paths to extracted PNG images.
        """
        output_dir = self._get_output_dir()
        extracted_paths = []

        for ts_ms in timestamps_ms:
            ts_sec = ts_ms / 1000.0
            output_path = output_dir / f"frame_{ts_ms}.png"

            if output_path.exists():
                extracted_paths.append(str(output_path))
                continue

            try:
                # Use ffmpeg to extract a single frame at the given timestamp
                # -ss before -i for fast seeking
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-ss", f"{ts_sec:.3f}",
                        "-i", self.video_path,
                        "-frames:v", "1",
                        "-q:v", "2",  # High quality
                        "-y",  # Overwrite
                        str(output_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0 and output_path.exists():
                    extracted_paths.append(str(output_path))
                    logger.debug(f"Extracted frame at {ts_sec}s -> {output_path}")
                else:
                    logger.warning(
                        f"Failed to extract frame at {ts_sec}s: {result.stderr[:200]}"
                    )
            except subprocess.TimeoutExpired:
                logger.error(f"ffmpeg timed out extracting frame at {ts_sec}s")
            except FileNotFoundError:
                logger.error(
                    "ffmpeg not found. Install it with: brew install ffmpeg"
                )
                break

        return extracted_paths

    async def extract_and_analyze(self, timestamps_ms: list[int]) -> list[dict]:
        """
        Extract keyframes and analyze them with Vision/OCR.

        Args:
            timestamps_ms: List of timestamps in milliseconds.

        Returns:
            List of dicts: [{timestamp_ms, screenshot_path, ocr_elements}, ...]
        """
        # Extract frames (CPU-bound, run in thread)
        loop = asyncio.get_event_loop()
        frame_paths = await loop.run_in_executor(
            None, self.extract_frames, timestamps_ms
        )

        results = []
        for ts_ms, frame_path in zip(timestamps_ms, frame_paths):
            result = {
                "timestamp_ms": ts_ms,
                "screenshot_path": frame_path,
                "ocr_elements": [],
            }

            # Try Vision analysis if available
            try:
                from app.core.vision.engine import vision_engine
                from app.core.vision.types import VisionTask

                # Use the singleton vision_engine
                vision_result = await vision_engine.process(
                    task=VisionTask.OCR,
                    image_source=frame_path
                )
                
                if vision_result.success:
                    # Convert UIElement objects to dicts for JSON serialization/easier handling
                    result["ocr_elements"] = [
                        {
                            "text": el.text,
                            "bounds": [el.x - el.width//2, el.y - el.height//2, el.width, el.height],
                            "center": [el.x, el.y]
                        }
                        for el in vision_result.elements
                    ]
            except Exception as e:
                logger.warning(f"Vision analysis skipped for {frame_path}: {e}")

            results.append(result)

        return results
