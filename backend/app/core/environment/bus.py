"""
Environment Domain Event Bus
============================

Domain-specific event bus for the Awakening/Environment module.

This bus handles internal environment orchestration (Discovery, Watchers, Atlas).
"""

import logging

from app.core.events.base import AsyncEventBus

logger = logging.getLogger(__name__)

# Environment domain-specific event bus
event_bus = AsyncEventBus("awakening")
