"""
Tools Event Types
=================

Event type constants for skill execution and evolution.
"""

from enum import Enum


class SkillEventType(str, Enum):
    """Skill evolution event types."""
    EXECUTED = "skill.executed"
    PROMOTED = "skill.promoted"
    DEPRECATED = "skill.deprecated"
