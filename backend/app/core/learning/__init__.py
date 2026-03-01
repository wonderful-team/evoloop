"""
Learning Ecosystem - Core Entry Point
Exposes key services and singletons for skill lifecycle management.
"""

from .discovery import SkillDiscovery, SkillMatch, skill_discovery
from .frame_compressor import (
    CompressedFrame,
    CoordinateNormalizer,
    FrameCompressor,
    KeyframeSelector,
)
from .multimodal_synthesizer import MultimodalSkillSynthesizer, RecordingSession
from .skill_synthesizer import WorkflowSynthesizer
from .trace_parser import TraceParser, TraceSequence

__all__ = [
    # 发现
    "skill_discovery",
    "SkillMatch",
    "SkillDiscovery",
    # 合成器
    "WorkflowSynthesizer",
    "MultimodalSkillSynthesizer",
    "RecordingSession",
    # 多模态
    "CompressedFrame",
    "CoordinateNormalizer",
    "FrameCompressor",
    "KeyframeSelector",
    # 解析
    "TraceParser",
    "TraceSequence",
]
