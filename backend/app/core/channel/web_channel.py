"""
WebChannel — SSE / MessageBroker transport for Web UI streaming.

Wraps the MessageBroker publish logic. The SSE consumer in
app/api/routes/stream.py subscribes to the same pub/sub channel.
"""

import json
import logging
from typing import Any

from app.core.engine.message.broker import get_message_broker
from app.core.engine.message.mapper import BlockMapper
from app.core.engine.message.schemas import MessageBlock
from app.models.schemas.events import BaseStreamEvent

from .base import Channel, ChannelContext

logger = logging.getLogger(__name__)


def format_event_for_frontend(event: Any) -> dict:
    """Format a core BaseEvent into the frontend-facing structure."""
    from app.core.engine.event.schemas import (
        AgentRunCompletedEvent,
        AgentSessionStartedEvent,
    )
    from app.core.events.base import BaseEvent
    from app.core.events.schemas import (
        SessionCompletedEvent,
    )
    from app.domain.planning.event.schemas import PlanUpdatedEvent
    from app.core.file.event.schemas import ChangesetUpdatedEvent
    from app.core.monitoring.event import (
        SystemLogEvent,
        SystemStatusEvent,
        ActivityStateRefreshedEvent,
    )
    from app.core.tools.event.schemas import (
        BackgroundTaskEvent,
        BackgroundTaskOutputEvent,
    )

    # Specific overrides matching historical to_frontend_payload outputs
    if isinstance(event, SessionCompletedEvent):
        return {
            "type": "session_completed",
            "thread_id": event.thread_id,
            "timestamp": event.timestamp.isoformat(),
            "data": event.data.model_dump(exclude={"messages", "blackboard_dict"}) if hasattr(event.data, "model_dump") else event.data
        }
    elif isinstance(event, SystemStatusEvent):
        return {
            "type": "status",
            "thread_id": event.thread_id,
            "status": event.status
        }
    elif isinstance(event, SystemLogEvent):
        return {
            "type": "system_log",
            "event": event.log_type,
            "data": event.log_data,
            "thread_id": event.thread_id,
            "timestamp": event.timestamp.isoformat()
        }
    elif isinstance(event, PlanUpdatedEvent):
        return {
            "type": "plan",
            "thread_id": event.thread_id,
            "plan_id": event.plan_id,
            "step_id": event.step_id,
            "status": event.status,
            "data": {
                "plan_id": event.plan_id,
                "step_id": event.step_id,
                "status": event.status,
            }
        }
    elif isinstance(event, ChangesetUpdatedEvent):
        return {
            "type": "changeset",
            "thread_id": event.thread_id,
            "message_id": event.message_id,
            "file_path": event.file_path,
            "operation": event.operation,
            "data": {
                "message_id": event.message_id,
                "file_path": event.file_path,
                "operation": event.operation,
            }
        }
    elif isinstance(event, ActivityStateRefreshedEvent):
        return {
            "type": "activity",
            **event.activity_state
        }
    elif isinstance(event, AgentSessionStartedEvent):
        return {
            "type": "run_start",
            "thread_id": event.thread_id,
            "run_id": None,  # Session start doesn't have a run_id yet
            "goal": "",
        }
    elif isinstance(event, AgentRunCompletedEvent):
        return {
            "type": "run_end",
            "thread_id": event.thread_id,
            "run_id": event.payload.get("run_id"),
            "status": event.status,
            "final_outcome": event.payload.get("outcome") or event.payload.get("summary"),
        }
    elif isinstance(event, BackgroundTaskEvent):
        return {
            "type": f"task_{event.action}",
            "task": event.task_data,
            "timestamp": event.timestamp.isoformat()
        }
    elif isinstance(event, BackgroundTaskOutputEvent):
        return {
            "type": "task_output",
            "task_id": event.task_id,
            "output": event.output,
            "timestamp": event.timestamp.isoformat()
        }
    elif isinstance(event, BaseEvent):
        event_str = event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
        return {
            "type": "system_event",
            "event": event_str,
            "thread_id": event.thread_id,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source,
            "data": event.data.model_dump() if hasattr(event.data, "model_dump") else event.data
        }

    # Fallback
    if hasattr(event, "model_dump"):
        return event.model_dump()
    return str(event)


class WebChannel(Channel):
    """SSE transport via the MessageBroker (local in-memory or Redis pub/sub)."""

    name = "sse"
    accepts_blocks = True
    accepts_stream_events = True

    async def send(
        self,
        payload: Any,
        ctx: ChannelContext,
    ) -> None:
        """Serialize payload and publish to the chat/system SSE channel."""
        from app.core.events.base import BaseEvent

        # Determine target channel name
        broadcast_channel = getattr(payload, "broadcast_channel", None)
        if broadcast_channel == "system" or not ctx.thread_id or ctx.thread_id == "system":
            channel = "system:events"
        else:
            channel = f"chat:{ctx.thread_id}:events"

        if isinstance(payload, MessageBlock):
            event = BlockMapper.to_sse(payload, action=ctx.action)
            data_json = event.model_dump_json()
        elif isinstance(payload, BaseStreamEvent):
            data_json = payload.model_dump_json(exclude_none=True)
        elif isinstance(payload, BaseEvent):
            formatted = format_event_for_frontend(payload)
            from app.utils.json import dumps as utils_dumps
            data_json = utils_dumps(formatted, ensure_ascii=False)
        elif hasattr(payload, "model_dump_json"):
            data_json = payload.model_dump_json(exclude_none=True)
        else:
            data_json = str(payload)

        broker = get_message_broker()
        await broker.publish(channel, data_json)

