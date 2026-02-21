"""
Learning Ecosystem - Core Entry Point
Exposes key services and singletons for skill lifecycle management.
"""

from .discovery import skill_discovery, SkillMatch, SkillDiscovery
from .skill_synthesizer import WorkflowSynthesizer
from .trace_parser import TraceParser, TraceSequence

__all__ = [
    "skill_discovery",
    "SkillMatch",
    "SkillDiscovery",
    "WorkflowSynthesizer",
    "TraceParser",
    "TraceSequence",
]
