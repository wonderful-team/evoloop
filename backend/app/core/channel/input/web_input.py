"""
WebInputChannel — normalizes chat messages from the web chat HTTP endpoint.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.channel.base import IncomingMessage, InputChannel

logger = logging.getLogger(__name__)


class WebInputChannel(InputChannel):
    """Web input: receives chat messages from the POST /chat endpoint."""

    name = "web"

    async def receive(self, raw: dict[str, Any], **kwargs: Any) -> IncomingMessage | None:
        """
        Build an IncomingMessage from a chat request.

        ``raw`` is the parsed request body (dict).
        Resolves skill references internally.
        """
        thread_id = str(raw.get("thread_id", "")).strip()
        text = str(raw.get("message") or raw.get("text", "")).strip()
        if not thread_id or not text:
            return None

        references = raw.get("references") or []
        skill_ids = raw.get("skill_ids")
        if skill_ids:
            try:
                from app.core.learning.skills.repository import skill_repository

                for skill in await skill_repository.get_by_ids(skill_ids):
                    references.append({
                        "id": str(skill.id),
                        "type": "skill",
                        "target_id": str(skill.id),
                        "target_name": skill.name,
                        "metadata": {
                            "skill_id": skill.id,
                            "skill_name": skill.name,
                            "description": skill.description,
                        },
                        "meta_data": {
                            "skill_id": skill.id,
                            "skill_name": skill.name,
                            "description": skill.description,
                        },
                    })
            except Exception as e:
                logger.warning("Failed to fetch skills %s: %s", skill_ids, e)

        meta: dict[str, Any] = {}
        try:
            from app.core.session.manager import session_manager

            session = session_manager.get(thread_id)
            if session is not None and session.worker is not None and not session.worker.done:
                meta["has_running_worker"] = "true"
                meta["running_worker_desc"] = session.worker.description
        except Exception:
            logger.warning("[WebInputChannel] session lookup failed", exc_info=True)

        return IncomingMessage(
            source="web",
            thread_id=thread_id,
            text=text,
            project_id=int(raw.get("project_id", 0)),
            references=references,
            command_id=raw.get("command_id"),
            checkpoint_id=raw.get("checkpoint_id"),
            model=raw.get("model"),
            context=kwargs.get("context"),
            member_id=kwargs.get("member_id", 0),
            is_retry=kwargs.get("is_retry", False),
            skip_message_persistence=kwargs.get("skip_message_persistence", False),
            metadata=meta,
        )


web_input = WebInputChannel()
