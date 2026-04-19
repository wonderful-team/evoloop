"""
Todo Memory Context Provider

Subscribes to memory.context_gather events and injects pending todo
context into memory extraction without creating circular core->domain dependencies.
"""

import logging

from app.core.events.decorators import event_register, event_subscribe
from app.core.memory.events import (
    MEMORY_CONTEXT_GATHER_EVENT_TYPE,
    MemoryContextGatherEvent,
)
from app.utils import render_template

logger = logging.getLogger(__name__)


@event_register()
class TodoMemoryContextProvider:
    """
    Provides pending todo context for memory extraction.

    Automatically registered via @event_register and discovered at startup.
    Renders its own markdown fragment via Jinja2 template — memory layer
    only sees the final formatted string.
    """

    @event_subscribe(MEMORY_CONTEXT_GATHER_EVENT_TYPE)
    async def on_context_gather(self, event: MemoryContextGatherEvent) -> None:
        """Render todo context fragment and append to event data."""
        project_id = event.data.project_id
        if not project_id:
            return

        try:
            from app.domain.todo.service import TodoService
            from app.infrastructure.database.sql.database import session_scope

            async with session_scope() as session:
                todo_service = TodoService(session)
                todos = await todo_service.list_pending_by_project(project_id)
                if todos:
                    fragment = render_template(
                        "domain/todo/memory_context.j2",
                        todos=[
                            {"title": t.title, "priority": t.priority}
                            for t in todos[:20]
                        ],
                    )
                    if fragment.strip():
                        event.data.context_fragments.append(fragment.strip())
        except Exception as e:
            logger.warning(f"[TodoContextProvider] Failed to render TODO context: {e}")
