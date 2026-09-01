"""
Video infrastructure schemas.
VideoInfo, CompressedFrame, and related models used by FrameExtractor and FrameCompressor.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class VideoInfo:
    """Metadata about a video file."""

    duration: float = 0.0  # seconds
    width: int = 0
    height: int = 0
    fps: float = 0.0
    path: str = ""


@dataclass
class CompressionConfig:
    """Configuration for frame compression."""

    max_width: int = 768
    quality: int = 85
    detail_level: str = "low"
    format: str = "JPEG"


@dataclass
class KeyframeCandidate:
    """A candidate keyframe to extract from a video."""

    timestamp: float
    context: str = ""
    description: str = ""
    priority: int = 0
    related_event: Any = None


@dataclass
class CompressedFrame:
    """A compressed video frame ready for LLM consumption."""

    data: bytes = b""
    width: int = 0
    height: int = 0
    original_size: tuple[int, int] = (0, 0)
    compression_ratio: float = 1.0
    detail_level: str = "low"
    timestamp: float = 0.0
    description: str = ""
    norm_events: list[dict[str, Any]] | None = None
