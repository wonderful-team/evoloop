"""Channel adapters for Layer-0 routed decisions.

This package contains the channel-specific presentation/execution layer for L0
routing decisions.  ``dispatch.py`` holds the channel-agnostic pipeline;
``voice.py`` and ``web.py`` implement the voice and web presenters respectively.
"""

from app.core.routing.channels.dispatch import (
    DispatchResult,
    RoutePresenter,
    dispatch_decision,
)
from app.core.routing.channels.voice import VoicePresenter, execute_route_for_voice
from app.core.routing.channels.web import WebPresenter, execute_route_for_web

__all__ = [
    "DispatchResult",
    "RoutePresenter",
    "dispatch_decision",
    "VoicePresenter",
    "execute_route_for_voice",
    "WebPresenter",
    "execute_route_for_web",
]
