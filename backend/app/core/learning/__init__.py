"""
Learning Ecosystem - Core Entry Point
Exposes key services and singletons for skill lifecycle management.
"""

from .discovery import skill_discovery, SkillMatch, SkillDiscovery
from .skill_synthesizer import WorkflowSynthesizer
from .skill_executor import SkillExecutor
from .trace_parser import TraceParser, TraceSequence
from .skill_optimizer import SkillOptimizer

__all__ = [
    "skill_discovery",
    "SkillMatch",
    "SkillDiscovery",
    "WorkflowSynthesizer",
    "SkillExecutor",
    "TraceParser",
    "TraceSequence",
    "SkillOptimizer",
]
