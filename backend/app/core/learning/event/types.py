"""
Skill Event Types
=================

Skill lifecycle event type constants for the learning domain.

Defined here (not in ``app.core.environment.event``) because skill execution,
promotion and deprecation are learning-domain concerns.
"""

from enum import Enum


class SkillEventType(str, Enum):
    """Skill lifecycle event types."""

    SKILL_EXECUTED = "skill.executed"
    SKILL_PROMOTED = "skill.promoted"
    SKILL_DEPRECATED = "skill.deprecated"
