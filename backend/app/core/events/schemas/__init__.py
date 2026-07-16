"""
Core Event Schemas
==================

Single source of truth for cross-cutting system lifecycle and status events.
Domain-specific events are defined in their respective modules.
"""

from .lifecycle import (
    AppStartedEvent,
    AppStoppingEvent,
    ConfigChangedEvent,
    SessionCompletedData,
    SessionCompletedEvent,
    SubscriptionChangedEvent,
    UserLoggedInEvent,
    UserLoggedOutEvent,
)

__all__ = [
    # Lifecycle
    "AppStartedEvent",
    "AppStoppingEvent",
    "SessionCompletedData",
    "SessionCompletedEvent",
    "SubscriptionChangedEvent",
    "UserLoggedInEvent",
    "UserLoggedOutEvent",
    "ConfigChangedEvent",
]
