"""A2A delegation event schemas.

Public lifecycle events (``is_public=True``) for remote A2A delegation
(docs/worker-delegation-design.md Phase D).

``A2ALifecycleEvent`` carries lifecycle status only (which device was delegated
to, the instruction, and the terminal result) so the frontend can render a live
"A2A 委派" panel without exposing internal execution details. Broadcast on the
caller thread so the SSE stream shows it.
"""

from app.core.events.base import BaseEvent
from app.core.events.constants import A2A_LIFECYCLE


class A2ALifecycleEvent(BaseEvent):
    """Public lifecycle status of one remote A2A delegation.

    ``status`` ∈ started | completed | failed | timeout | cancelled.
    ``thread_id`` is the caller thread that delegated the task.
    """

    event_type: str = A2A_LIFECYCLE
    thread_id: str  # caller thread_id
    task_id: str
    target_device_key: str = ""
    target_device_name: str = ""
    instruction: str = ""
    status: str  # started | completed | failed | timeout | cancelled
    result: str = ""
    error: str | None = None
    is_public: bool = True
    broadcast_channel: str = "chat"
