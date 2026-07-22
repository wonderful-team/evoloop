"""
MobileInputChannel — normalizes chat messages from the mobile relay.

The caller (``EngineCommandSubscriber``) handles transport-level concerns:
command validation, ack sending, payload extraction. It then passes the
inner payload dict to ``receive()``.
"""

from __future__ import annotations

from typing import Any

from app.core.channel.base import IncomingMessage, InputChannel


class MobileInputChannel(InputChannel):
    """Mobile input: receives chat commands relayed via EvoCloud Gateway."""

    name = "mobile"

    async def receive(self, raw: dict[str, Any], **kwargs: Any) -> IncomingMessage | None:
        """
        Build an IncomingMessage from a mobile chat payload.

        ``raw`` is the ``payload`` of a ``command.relay`` envelope with action ``"chat"``.
        Transport-level fields (``thread_id``, ``command_id``, ``message_id``) come
        from the outer envelope via ``kwargs``.
        """
        text = str(raw.get("text", "")).strip()
        references = raw.get("references")

        thread_id = str(kwargs.get("thread_id", "")).strip()
        if not thread_id:
            return None

        from app.constants import DEFAULT_PROJECT_ID
        from app.core.context.thread_store import thread_context_store

        pid = int(raw.get("project_id", 0)) or thread_context_store.get_active_project("remote-default") or DEFAULT_PROJECT_ID
        member_id = kwargs.get("member_id", 0)
        command_id = kwargs.get("command_id")
        message_id = kwargs.get("message_id")

        return IncomingMessage(
            source="mobile",
            thread_id=thread_id,
            text=text,
            project_id=pid,
            references=references,
            command_id=command_id,
            member_id=member_id,
            message_id=message_id,
        )


mobile_input = MobileInputChannel()
