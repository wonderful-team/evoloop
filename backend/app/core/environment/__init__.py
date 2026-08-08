"""
Evoloop Awakening System - Agent Environment Awareness Module.

Provides the Agent with a comprehensive understanding of its
operating environment, available resources, and capability boundaries.
"""

from app.core.environment.context_plugin import EnvironmentContextPlugin
from app.core.environment.lifecycle import _refresh_state as _refresh_state
from app.core.environment.lifecycle import awaken
from app.core.environment.models import AwakenedState
from app.core.environment.state import get_awakened_state
from app.core.environment.utils import (
    collect_cpu_mem,
    format_app_rankings,
    get_current_app_context,
    get_telemetry_dict,
)

__all__ = [
    "awaken",
    "format_app_rankings",
    "get_awakened_state",
    "get_current_app_context",
    "collect_cpu_mem",
    "get_telemetry_dict",
    "AwakenedState",
    "EnvironmentContextPlugin",
]
