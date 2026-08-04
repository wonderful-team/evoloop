"""
Evoloop Awakening System - Agent Environment Awareness Module.

Provides the Agent with a comprehensive understanding of its
operating environment, available resources, and capability boundaries.
"""

from app.core.environment.context_plugin import EnvironmentContextPlugin
from app.core.environment.formatting import format_app_rankings
from app.core.environment.lifecycle import _refresh_network_state as _refresh_network_state
from app.core.environment.lifecycle import _refresh_state as _refresh_state
from app.core.environment.lifecycle import awaken
from app.core.environment.models import AwakenedState
from app.core.environment.state import get_awakened_state

__all__ = [
    "awaken",
    "format_app_rankings",
    "get_awakened_state",
    "AwakenedState",
    "EnvironmentContextPlugin",
]
