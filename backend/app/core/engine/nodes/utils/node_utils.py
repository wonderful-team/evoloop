"""
Shared utilities for EvoLoop engine nodes.

Extracts cross-cutting concerns (logging, state resolution, signal dispatch)
to eliminate duplication across BaseAgentNode, FinishNode, AggregatorNode, etc.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def resolve_is_subtask(state: Any) -> bool:
    """
    Resolve `is_subtask` from state.
    """
    return state.is_subtask
