"""
Todo Module Event Subscribers
=============================

Handles todo lifecycle (harvesting), memory context provision, and rewind cleanup.
"""

import asyncio
import logging
from typing import List

from pydantic import Field
from sqlalchemy import delete, select

from app.core.engine.rewind.event import RewindEventType, RewindRequestedEvent
from app.core.events import SystemEventType
from app.core.events.base import AsyncEventBus
from app.core.events.decorators import event_register, event_subscribe, register_instance_handlers
from app.core.events.schemas import SessionCompletedEvent
from app.core.memory.event import (
    MEMORY_CONTEXT_GATHER_EVENT_TYPE,
    MemoryContextGatherEvent,
)
from app.domain.todo.event.schemas import TodoCleanupEvent
from app.infrastructure.database.sql.database import session_scope
from app.utils import render_template
from app.domain.todo.service import TodoService
from app.domain.todo.schemas import TodoHarvestingResult, TodoCreate
from app.infrastructure.config.service import SystemConfigService
from app.core.llm import InternalLLMService

logger = logging.getLogger(__name__)


@event_register()
class TodoLifecycleSubscriber:
    """
    Handles automatic Todo extraction from session history.
    """

    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_session_completed(self, event: SessionCompletedEvent):
        """
        Triggered when a session finishes successfully.
        Extracts future tasks and coordination items.
        """
        data = event.data
        logger.info(f"[Todo] 📝 Session completed for {data.thread_id}. Checking for pending actions...")

        # Initialize background context for extraction
        from app.core.context.manager import ContextManager, EvoContext
        ctx = EvoContext(
            thread_id=data.thread_id,
            project_id=data.project_id,
            active_model=data.model
        )
        token = ContextManager.set(ctx)

        try:
            # Trigger background harvesting task
            asyncio.create_task(self._harvest_todos(data))
        finally:
            ContextManager.reset(token)

    async def _harvest_todos(self, data):
        """Internal background method for deep analysis and storage."""
        thread_id = data.thread_id
        project_id = data.project_id
        model = data.model

        # 1. Check feature flags / settings
        auto_extract = SystemConfigService.get_value("AUTO_TODO_EXTRACTION", "true").lower() == "true"
        if not auto_extract:
            logger.debug(f"[Todo] Auto-extraction disabled for thread {thread_id}")
            return

        logger.info(f"[Todo] 🧠 Harvesting todos for thread {thread_id}...")

        try:
            # 2. Prepare context and history
            from app.core.engine.message.repository import MessageRepository
            repo = MessageRepository(thread_id=thread_id, project_id=project_id)
            db_messages, _, _ = await repo.get_full_history()
            
            if not db_messages:
                logger.debug(f"[Todo] No messages found for thread {thread_id}, skipping")
                return

            user_lang = SystemConfigService.get_language_preference()
            
            # 3. Render prompt
            prompt_text = render_template(
                "core/todo/extraction.prompt.j2",
                thread_id=thread_id,
                user_language=user_lang,
                messages=[{"role": m.role, "content": m.content} for m in db_messages],
                summary_needed=True
            )

            # 4. Call InternalLLMService
            model_name = SystemConfigService.get_value("LLM_MODEL")
            result = await InternalLLMService.invoke_structured(
                messages=[{"role": "system", "content": prompt_text}],
                purpose="todo_extraction",
                output_schema=TodoHarvestingResult,
                temperature=0.0,
                model_name=model_name
            )

            if not result.todos:
                logger.info(f"[Todo] No pending tasks identified for thread {thread_id}")
                return

            # 5. Persist valid extractions
            async with session_scope() as session:
                service = TodoService(session)
                count = 0
                for ext in result.todos:
                    if ext.confidence < 0.7:
                        continue
                    
                    await service.create(
                        TodoCreate(
                            title=ext.title,
                            description=ext.description,
                            priority=ext.priority,
                            category=ext.category,
                            project_id=project_id
                        ),
                        source_conversation_id=thread_id
                    )
                    count += 1
                
                logger.info(f"[Todo] ✅ Successfully harvested {count} todos for thread {thread_id}")

        except Exception as e:
            logger.error(f"[Todo] Harvesting failed for thread {thread_id}: {e}")


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


@event_register()
class TodoRewind:
    """Event-driven todo cleanup handler for rewind operations."""

    def __init__(self):
        self._deleted_count = 0

    @classmethod
    def register(cls, bus: AsyncEventBus) -> "TodoRewind":
        """
        Register this handler to the event bus.
        
        Args:
            bus: The event bus to subscribe to
            
        Returns:
            The handler instance
        """
        instance = cls()
        register_instance_handlers(instance, bus)
        return instance

    @event_subscribe(RewindEventType.REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        """
        Handle main rewind event - prepare todo cleanup.
        
        Uses event.affected_message_ids (pre-computed by RewindOrchestrator)
        to avoid race conditions with other handlers querying the messages table.
        """
        message_ids = event.affected_message_ids or await self._find_message_ids(
            thread_id=event.thread_id,
            target_message_id=event.target_message_id,
            include_target=event.include_target
        )
        
        if message_ids or event.affected_run_ids:
            count = await self._delete_todos(
                message_ids=message_ids,
                run_ids=event.affected_run_ids
            )
            self._deleted_count = count
            event.results["todos"] = count

            from app.domain.todo.event.publishers import publish_todo_cleanup
            await publish_todo_cleanup(
                thread_id=event.thread_id,
                source_message_ids=message_ids,
                affected_run_ids=event.affected_run_ids
            )
            logger.info(f"[TodoRewind] Deleted {count} todo items for thread {event.thread_id}")
        else:
            logger.debug(f"[TodoRewind] No todo items found to delete for thread {event.thread_id}")

    @event_subscribe(RewindEventType.TODO_CLEANUP)
    async def _handle_todo_cleanup(self, event: "TodoCleanupEvent") -> None:
        """
        Handle specific todo cleanup event.
        
        This performs the actual todo deletion.
        """
        try:
            count = await self._delete_todos(
                message_ids=event.source_message_ids,
                run_ids=event.affected_run_ids
            )
            self._deleted_count = count
            logger.info(f"[TodoRewind] Deleted {count} todo items")
        except Exception as e:
            logger.error(f"[TodoRewind] Todo cleanup failed: {e}")
            raise

    async def _find_message_ids(
        self,
        thread_id: str,
        target_message_id: str | None,
        include_target: bool
    ) -> list[str]:
        """Find message IDs to clean up for the given thread."""
        from app.models import Message
        
        async with session_scope() as session:
            stmt = select(Message.id).where(Message.thread_id == thread_id)
            
            if target_message_id:
                # Resolve sequence from UUID
                stmt_target = select(Message.sequence_number).where(Message.id == target_message_id)
                res_target = await session.execute(stmt_target)
                target_seq = res_target.scalar_one_or_none()
                
                if target_seq is None:
                    logger.warning(f"[TodoRewind] Target message {target_message_id} not found")
                    return []

                if include_target:
                    stmt = stmt.where(Message.sequence_number >= target_seq)
                else:
                    stmt = stmt.where(Message.sequence_number > target_seq)

            result = await session.execute(stmt)
            return [str(row[0]) for row in result.all()]

    async def _delete_todos(
        self,
        message_ids: list[str],
        run_ids: list[str] | None = None
    ) -> int:
        """
        Delete todo items by message IDs or run IDs.
        """
        from app.models.todo import TodoItem
        
        if not message_ids and not run_ids:
            return 0
            
        async with session_scope() as session:
            stmt = delete(TodoItem)
            
            conditions = []
            if message_ids:
                conditions.append(TodoItem.source_message_id.in_(message_ids))
            if run_ids:
                conditions.append(TodoItem.run_id.in_(run_ids))
                
            if len(conditions) > 1:
                from sqlalchemy import or_
                stmt = stmt.where(or_(*conditions))
            else:
                stmt = stmt.where(conditions[0])
                
            result = await session.execute(stmt)
            count = result.rowcount
            logger.info(f"[TodoRewind] Deleted {count} todo items")
            return count

    async def cleanup(self, message_ids: list[str], **kwargs) -> int:
        """Direct cleanup entry point (non-event-driven usage)."""
        return await self._delete_todos(message_ids=message_ids)

    def get_deleted_count(self) -> int:
        """Get the count of todos deleted in the last operation."""
        return self._deleted_count
