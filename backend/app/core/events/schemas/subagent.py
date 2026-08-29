"""Subagent event schemas.

Internal events (``is_public=False``): never forwarded to SSE/user channels.
Design: docs/subagent-design.md §3.3 / §5.5.

``SubagentLifecycleEvent`` is the only public (``is_public=True``) subagent event:
it carries *lifecycle status only* (which subagents are running / finished), so
the frontend can render a live "active subagents" panel without exposing any
subagent-internal tool calls or text (R3 keeps those invisible to user channels).
"""

from typing import Any

from app.core.engine.state.subagent_schemas import SubagentNeedInput
from app.core.events.base import BaseEvent

SUBAGENT_COMPLETED = "subagent.completed"
SUBAGENT_HITL_REQUEST = "subagent.hitl_request"
SUBAGENT_LIFECYCLE = "subagent"


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


class SubagentCompletedEvent(BaseEvent):
    """Published by the subagent done_callback when a subagent reaches a terminal state."""

    event_type: str = SUBAGENT_COMPLETED
    thread_id: str  # parent thread_id
    subagent_id: str
    subagent_thread_id: str  # sub_tid
    status: str  # completed | failed | cancelled
    result: str = ""
    error: str | None = None
    tools_used: list[str] = []
    need_input: SubagentNeedInput | None = None  # Phase B
    is_public: bool = False


class SubagentHITLRequestEvent(BaseEvent):
    """subagent triggered a HITL request; transparently forward to the parent session.

    Design: docs/subagent-design.md §5.5. The parent Supervisor asks the user in the
    main session, then routes the answer back via ``respond_subagent_hitl``.
    """

    event_type: str = SUBAGENT_HITL_REQUEST
    thread_id: str  # parent thread_id (routing key)
    subagent_thread_id: str
    subagent_id: str
    request_type: str  # ask_human | ask_confirm | approval | secure_credential
    prompt: str
    options: list[str] = []
    context: str = ""
    tool_call_id: str
    risk_level: str | None = None
    resource_path: str | None = None
    is_public: bool = False

    def model_dump_hitl(self) -> dict[str, Any]:
        """Serialize to the payload stored in the parent's pending_subagent_hitl_requests."""
        return {
            "subagent_thread_id": self.subagent_thread_id,
            "subagent_id": self.subagent_id,
            "request_type": self.request_type,
            "prompt": self.prompt,
            "options": self.options,
            "context": self.context,
            "tool_call_id": self.tool_call_id,
            "risk_level": self.risk_level,
            "resource_path": self.resource_path,
        }
