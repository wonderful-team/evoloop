import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, RemoveMessage
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.globals import get_graph
from app.core.monitoring.activity import activity_monitor
from app.core.persistence import get_db_pool
from app.infrastructure.database.sql.database import get_db_session
from app.models import Conversation, Message

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Schemas ---


class SearchResult(BaseModel):
    thread_id: str
    role: str
    content: str
    created_at: str
    match_snippet: str | None = None


class RenameRequest(BaseModel):
    title: str


class ConversationListItem(BaseModel):
    thread_id: str
    title: str
    project_id: int | None
    updated_at: datetime | None
    status: str = "idle"


class ReferenceItem(BaseModel):
    id: str
    type: str
    target_id: str
    target_name: str


class ToolStep(BaseModel):
    id: str
    tool: str
    input: dict | str
    output: str
    status: str = "success"
    duration: float | None = None


class MessageItem(BaseModel):
    id: str
    type: str
    content: str
    thinking: str | None
    created_at: str | None
    steps_snapshot: list[dict] | None = None  # Phase 6: Historical task steps
    run_id: str | None = None  # Phase 8: Deep Linking
    parent_id: int | None = None  # Phase 8: Threading
    references: list[ReferenceItem] = []  # Phase 9: Persistent References
    steps: list[ToolStep] = []  # Phase 24: Tool Execution Steps


class RewindResponse(BaseModel):
    status: str
    thread_id: str
    removed_count: int = 0


@router.get("/", response_model=list[ConversationListItem])
async def list_conversations(project_id: int | None = None):
    """
    List conversations, optionally filtered by project.
    """
    async with get_db_session() as session:
        stmt = select(Conversation).order_by(Conversation.updated_at.desc())
        if project_id:
            stmt = stmt.where(Conversation.project_id == project_id)

        result = await session.execute(stmt)
        conversations = result.scalars().all()

        # Fetch active statuses
        thread_ids = [c.id for c in conversations]
        status_map = await activity_monitor.get_statuses(thread_ids)

        return [
            ConversationListItem(
                thread_id=c.id,
                title=c.title or "Untitled",
                project_id=c.project_id,
                updated_at=c.updated_at,
                status=status_map.get(c.id, "idle"),
            ) for c in conversations
        ]


@router.get("/{thread_id}/messages", response_model=list[MessageItem])
async def get_conversation_messages(thread_id: str):
    """
    Get message history for a thread from the persistent SQL log.
    Includes steps_snapshot for historical task visualization.
    """
    try:
        async with get_db_session() as session:
            # Optimize: Eager load references
            stmt = (
                select(Message)
                .where(Message.thread_id == thread_id)
                .options(selectinload(Message.references))
                .order_by(Message.id.asc())
            )
            result = await session.execute(stmt)
            db_messages = result.scalars().all()

            # Phase 24: Server-Side Tool Folding
            # We aggregate 'tool' messages into the 'steps' of the preceding 'ai' message.
            final_items = []
            last_ai_item: MessageItem | None = None
            pending_tool_calls = []  # FIFO queue of (id, name, args) derived from AI message

            for m in db_messages:
                # 1. Parse References (Common)
                refs = (
                    [
                        ReferenceItem(
                            id=ref.id,
                            type=ref.type,
                            target_id=ref.target_id,
                            target_name=ref.target_name,
                        )
                        for ref in m.references
                    ]
                    if m.references
                    else []
                )

                # 2. Handle Message Types
                if m.role == "human":
                    item = MessageItem(
                        id=str(m.id),
                        type="human",
                        content=m.content,
                        thinking=m.thinking,
                        created_at=m.created_at.isoformat() if m.created_at else None,
                        steps_snapshot=m.steps_snapshot,
                        run_id=m.run_id,
                        parent_id=m.parent_id,
                        references=refs,
                        steps=[],
                    )
                    final_items.append(item)
                    last_ai_item = None
                    pending_tool_calls = []

                elif m.role == "ai" or m.role == "assistant":
                    item = MessageItem(
                        id=str(m.id),
                        type="ai",  # Normalize to "ai" for frontend
                        content=m.content,
                        thinking=m.thinking,
                        created_at=m.created_at.isoformat() if m.created_at else None,
                        steps_snapshot=m.steps_snapshot,
                        run_id=m.run_id,
                        parent_id=m.parent_id,
                        references=refs,
                        steps=[],
                    )

                    # Store as potential parent for subsequent tool outputs
                    final_items.append(item)
                    last_ai_item = item

                    # Parse tool calls to create linking queue
                    if m.tool_calls:
                        # tool_calls is a list of dicts: [{id, name, args}, ...]
                        # We copy it to consume as we find tool outputs
                        pending_tool_calls = list(m.tool_calls) if isinstance(m.tool_calls, list) else []

                elif m.role == "tool":
                    # Fold into last AI message if available
                    if last_ai_item and pending_tool_calls:
                        # Match FIFO (Assuming Sequential Execution)
                        call_info = pending_tool_calls.pop(0)

                        step = ToolStep(
                            id=call_info.get("id", "unknown"),
                            tool=call_info.get("name", "unknown"),
                            input=call_info.get("args", {}),
                            output=m.tool_output or m.content or "",  # Prefer tool_output column
                            status="success",
                        )
                        last_ai_item.steps.append(step)
                    else:
                        # Orphaned tool message or mismatch
                        # For now, we HIDE it to prevent clutter, as per requirement.
                        # If strict debugging is needed, valid tool messages should have a parent.
                        pass

            return final_items

    except Exception as e:
        logger.error(f"Failed to fetch history for {thread_id}: {e}")
        return []


@router.get("/search", response_model=list[SearchResult])
async def search_conversations(q: str, project_id: int | None = None):
    """
    Full-text search on message logs.
    """
    if not q or len(q.strip()) < 2:
        return []

    async with get_db_session() as session:
        stmt = select(Message).where(Message.content.ilike(f"%{q}%"))

        if project_id:
            stmt = stmt.where(Message.project_id == project_id)

        stmt = stmt.order_by(Message.created_at.desc()).limit(20)

        result = await session.execute(stmt)
        logs = result.scalars().all()

        return [
            SearchResult(
                thread_id=log.thread_id,
                role=log.role,
                content=log.content,
                created_at=str(log.created_at),
                match_snippet=log.content[:200],
            )
            for log in logs
        ]


@router.patch("/{thread_id}")
async def rename_conversation(thread_id: str, req: RenameRequest):
    """
    Rename a conversation.
    """
    async with get_db_session() as session:
        conversation = await session.get(Conversation, thread_id)
        if not conversation:
            raise HTTPException(404, "Conversation not found")

        conversation.title = req.title
        await session.commit()

    return {"status": "updated", "thread_id": thread_id, "title": req.title}


@router.get("/{thread_id}/activity")
async def get_thread_activity(thread_id: str):
    """Get real-time activity/status for a thread run."""
    return await activity_monitor.get_activity(thread_id)


@router.delete("/{thread_id}")
async def delete_conversation(thread_id: str):
    """Delete a conversation history and its checkpoints."""
    db_pool = get_db_pool()
    if not db_pool:
        raise HTTPException(503, "Database not initialized")

    try:
        # 1. Delete Checkpoints (Binary)
        async with db_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))
                await cur.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (thread_id,))

        # 2. Delete Thread Metadata & Logs
        async with get_db_session() as session:
            # Delete Conversation
            conversation = await session.get(Conversation, thread_id)
            if conversation:
                await session.delete(conversation)

            # Delete Logs (Bulk delete)
            await session.execute(delete(Message).where(Message.thread_id == thread_id))
            await session.commit()

        return {"status": "deleted", "thread_id": thread_id}
    except Exception as e:
        logger.error(f"Failed to delete conversation: {e}")
        raise HTTPException(500, str(e))


@router.post("/{thread_id}/rewind", response_model=RewindResponse)
async def rewind_conversation(thread_id: str):
    """
    Rewind the conversation to the previous state (Undo last step).
    """
    graph = get_graph()

    if not graph:
        raise HTTPException(503, "Graph unavailable")

    config = {"configurable": {"thread_id": thread_id}}
    state = await graph.aget_state(config)

    if not state.values:
        return {"status": "empty", "thread_id": thread_id}

    messages = state.values.get("messages", [])
    if not messages:
        return {"status": "empty", "thread_id": thread_id}

    # Find the last HumanMessage
    to_delete = []

    # Iterate backwards
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        to_delete.append(msg)
        if isinstance(msg, HumanMessage):
            break

    if not to_delete:
        return {
            "status": "no_human_message_found",
            "thread_id": thread_id,
            "removed_count": 0,
        }

    updates = []
    for m in to_delete:
        if hasattr(m, "id") and m.id:
            updates.append(RemoveMessage(id=m.id))

    if updates:
        # 1. Update Graph State
        await graph.aupdate_state(config, {"messages": updates})

        # 2. Sync DB
        msg_ids = [u.id for u in updates]
        if msg_ids:
            try:
                async with get_db_session() as session:
                    await session.execute(
                        delete(Message).where(Message.id.in_(msg_ids))
                    )
                    await session.commit()
                logger.info(f"DB Sync: Deleted {len(msg_ids)} messages.")
            except Exception as e:
                logger.error(f"DB Sync Failed during rewind: {e}")

        return {
            "status": "rewound",
            "removed_count": len(updates),
            "thread_id": thread_id,
        }
    else:
        return {"status": "failed_no_ids", "thread_id": thread_id, "removed_count": 0}
