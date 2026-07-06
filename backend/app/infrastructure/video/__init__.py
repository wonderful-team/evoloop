"""
Video infrastructure — frame extraction, compression, and metadata.

Usage:
    from app.infrastructure.video.extractor import FrameExtractor
    from app.infrastructure.video.compressor import FrameCompressor, KeyframeSelector, CoordinateNormalizer
    from app.infrastructure.video.schemas import VideoInfo, CompressedFrame, KeyframeCandidate
"""

from app.infrastructure.video.compressor import (
    CompressionStrategy,
    CoordinateNormalizer,
    FrameCompressor,
    KeyframeSelector,
)
from app.infrastructure.video.extractor import FrameExtractor
from app.infrastructure.video.schemas import (
    CompressedFrame,
    CompressionConfig,
    KeyframeCandidate,
    VideoInfo,
)
from app.infrastructure.video.service import VideoService

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
