"""
MobileInputChannel — normalizes chat messages from the mobile relay.

The caller (``EngineCommandSubscriber``) handles transport-level concerns:
command validation, ack sending, payload extraction. It then passes the
inner payload dict to ``receive()``.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.channel.base import IncomingMessage, InputChannel

logger = logging.getLogger(__name__)


class MobileInputChannel(InputChannel):
    """Mobile input: receives chat commands relayed via EvoCloud Gateway."""

    name = "mobile"

    async def receive(self, raw: dict[str, Any], **kwargs: Any) -> IncomingMessage | None:
        """
        Build an IncomingMessage from a mobile chat payload.

        ``raw`` is the ``payload`` of a ``command.relay`` envelope with action ``"chat"``.
        Transport-level fields (``thread_id``, ``command_id``, ``message_id``) come
        from the outer envelope via ``kwargs``；当经 ``dispatch_user_message`` 统一
        路由时这些字段会并入 ``raw``，因此 kwargs 缺失时回退到 raw。
        """
        text = str(raw.get("text", "")).strip()
        references = raw.get("references")

        thread_id = str(kwargs.get("thread_id") or raw.get("thread_id") or "").strip()
        if not thread_id:
            return None

        from app.constants import DEFAULT_PROJECT_ID
        from app.core.context.thread_store import thread_context_store

        # SSOT：项目上下文以 shared_state 为准；raw 显式指定非 0 时视为切换并同步。
        req_pid = int(raw.get("project_id", 0))
        if req_pid:
            from app.core.state import shared_state

            await shared_state.set_active_project_id(req_pid)
            pid = req_pid
        else:
            from app.core.state import shared_state

            pid = await shared_state.get_active_project_id()
            if not pid:
                pid = thread_context_store.get_active_project("remote-default") or DEFAULT_PROJECT_ID
        member_id = kwargs.get("member_id") or raw.get("member_id") or 0
        command_id = kwargs.get("command_id") or raw.get("command_id")
        message_id = kwargs.get("message_id") or raw.get("message_id")

        meta: dict[str, Any] = {}
        try:
            from app.core.engine.session.manager import session_manager

            session = session_manager.get(thread_id)
            if session is not None and session.worker is not None and not session.worker.done:
                meta["has_running_worker"] = "true"
                meta["running_worker_desc"] = session.worker.description
        except Exception:
            logger.warning("[MobileInputChannel] session lookup failed", exc_info=True)

        return IncomingMessage(
            source="mobile",
            thread_id=thread_id,
            text=text,
            project_id=pid,
            references=references,
            command_id=command_id,
            member_id=member_id,
            message_id=message_id,
            metadata=meta,
        )


mobile_input = MobileInputChannel()
