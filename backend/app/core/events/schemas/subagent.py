"""Subagent event schemas.

Internal events (``is_public=False``): never forwarded to SSE/user channels.
Design: docs/subagent-design.md §3.3 / §5.5.

``SubagentLifecycleEvent`` is the only public (``is_public=True``) subagent event:
it carries *lifecycle status only* (which subagents are running / finished), so
the frontend can render a live "active subagents" panel without exposing any
subagent-internal tool calls or text (R3 keeps those invisible to user channels).
"""

from app.core.events.base import BaseEvent
from app.core.events.constants import SUBAGENT_LIFECYCLE


class SubagentLifecycleEvent(BaseEvent):
    """Public lifecycle status of one subagent, bridged to the parent SSE stream.

    ``status`` ∈ started | completed | failed | cancelled. Broadcast on the parent
    thread so the frontend can show a live subagent panel.
    """

    event_type: str = SUBAGENT_LIFECYCLE
    thread_id: str  # parent thread_id
    subagent_id: str
    subagent_thread_id: str  # sub_tid
    instruction: str = ""
    status: str  # started | completed | failed | cancelled
    result: str = ""
    error: str | None = None
    is_public: bool = True
    broadcast_channel: str = "chat"
