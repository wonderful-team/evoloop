"""
Evoloop Awakening System - Agent Environment Awareness Module.

Provides the Agent with a comprehensive understanding of its
operating environment, available resources, and capability boundaries.
"""

from app.core.environment.context_plugin import EnvironmentContextPlugin
from app.core.environment.lifecycle import (
    _refresh_network_state,
    _refresh_state,
    awaken,
)
from app.core.environment.models import AwakenedState
from app.core.environment.state import get_awakened_state

__all__ = [
    "awaken",
    "get_awakened_state",
    "AwakenedState",
    "EnvironmentContextPlugin",
]
