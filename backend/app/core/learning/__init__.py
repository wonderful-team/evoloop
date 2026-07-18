"""
Learning Ecosystem - Core Entry Point
Exposes key services and singletons for skill lifecycle management.
"""

from .discovery import SkillDiscovery, SkillMatch, skill_discovery
from .multimodal_synthesizer import MultimodalSkillSynthesizer, RecordingSession
from .trace_parser import TraceParser, TraceSequence
from .workflow_synthesizer import WorkflowSynthesizer

__all__ = [
    # 发现
    "skill_discovery",
    "SkillMatch",
    "SkillDiscovery",
    # 合成器
    "WorkflowSynthesizer",
    "MultimodalSkillSynthesizer",
    "RecordingSession",
    # 解析
    "TraceParser",
    "TraceSequence",
]
