"""
Video infrastructure — frame extraction, compression, and metadata.

Usage:
    from app.infrastructure.vision.video.extractor import FrameExtractor
    from app.infrastructure.vision.video.compressor import FrameCompressor, KeyframeSelector, CoordinateNormalizer
    from app.infrastructure.vision.video.schemas import VideoInfo, CompressedFrame, KeyframeCandidate
"""

from app.infrastructure.vision.video.compressor import (
    CompressionStrategy,
    CoordinateNormalizer,
    FrameCompressor,
    KeyframeSelector,
)
from app.infrastructure.vision.video.extractor import FrameExtractor
from app.infrastructure.vision.video.schemas import (
    CompressedFrame,
    CompressionConfig,
    KeyframeCandidate,
    VideoInfo,
)
from app.infrastructure.vision.video.service import VideoService

__all__ = [
    "CompressedFrame",
    "CompressionConfig",
    "CompressionStrategy",
    "CoordinateNormalizer",
    "FrameCompressor",
    "FrameExtractor",
    "KeyframeCandidate",
    "KeyframeSelector",
    "VideoInfo",
    "VideoService",
]
