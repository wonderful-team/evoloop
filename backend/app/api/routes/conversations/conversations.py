import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.deps import CurrentUser
from app.api.schemas.conversations import (
    ConversationDeleteResponse,
    ConversationListItem,
    ConversationListResponse,
    ConversationUpdateRequest,
    ConversationUpdateResponse,
)
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.database import session_scope
from app.models import Conversation

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/", response_model=ConversationListResponse)
async def list_conversations(
    project_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: CurrentUser = None,
):
    async with session_scope() as session:
        count_stmt = select(func.count(Conversation.id)).where(Conversation.parent_thread_id.is_(None))
        if project_id is not None:
            count_stmt = count_stmt.where(Conversation.project_id == project_id)
        count_stmt = count_stmt.where(Conversation.member_id == current_user.id)
        total_count_result = await session.execute(count_stmt)
        total_count = total_count_result.scalar() or 0

        stmt = (
            select(Conversation)
            .where(Conversation.parent_thread_id.is_(None))
            .order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc())
        )
        if project_id is not None:
            stmt = stmt.where(Conversation.project_id == project_id)
        stmt = stmt.where(Conversation.member_id == current_user.id)

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await session.execute(stmt)
        conversations = result.scalars().all()

        thread_ids = [c.id for c in conversations]
        activity_map = await activity_monitor.get_statuses(thread_ids)

        items = [
            ConversationListItem(
                thread_id=c.id,
                title=c.title or "Untitled",
                project_id=c.project_id,
                updated_at=c.updated_at,
                status=activity_map.get(c.id, {}).get("status", "idle"),
                is_pinned=c.is_pinned,
                goal=activity_map.get(c.id, {}).get("main_goal"),
                parent_thread_id=c.parent_thread_id,
                root_thread_id=c.root_thread_id,
                caller_device_key=c.caller_device_key,
                executor_device_key=c.executor_device_key,
                executor_device_name=c.executor_device_name,
            ) for c in conversations
        ]

        return ConversationListResponse(
            data=items,
            total=total_count,
            page=page,
            page_size=page_size,
            success=True,
            message="Successfully retrieved conversations",
        )


@router.patch("/{thread_id}", response_model=ConversationUpdateResponse)
async def update_conversation(
    thread_id: str,
    req: ConversationUpdateRequest,
    current_user: CurrentUser = None,
):
    async with session_scope() as session:
        conversation = await session.get(Conversation, thread_id)
        if not conversation:
            raise HTTPException(404, "Conversation not found")

        if conversation.member_id != 0 and conversation.member_id != current_user.id:
            raise HTTPException(403, "Access denied")

        if req.title is not None:
            conversation.title = req.title
        if req.is_pinned is not None:
            conversation.is_pinned = req.is_pinned

        title = conversation.title
        is_pinned = conversation.is_pinned

    return ConversationUpdateResponse(
        status="updated",
        thread_id=thread_id,
        title=title,
        is_pinned=is_pinned,
    )


@router.get("/{thread_id}/activity")
async def get_thread_activity(
    thread_id: str,
    current_user: CurrentUser = None,  # noqa: ARG001
):
    return await activity_monitor.get_activity(thread_id)


@router.delete("/{thread_id}")
async def delete_conversation(
    thread_id: str,
    current_user: CurrentUser = None,
):
    try:
        async with session_scope() as session:
            conversation = await session.get(Conversation, thread_id)
            if conversation and conversation.member_id != 0 and conversation.member_id != current_user.id:
                raise HTTPException(403, "Access denied")

        from app.core.engine.event.publishers import publish_conversation_deleted

        await publish_conversation_deleted(thread_id)

        async with session_scope() as session:
            conversation = await session.get(Conversation, thread_id)
            if conversation:
                await session.delete(conversation)

        return ConversationDeleteResponse(status="deleted", thread_id=thread_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete conversation: {e}")
        raise HTTPException(500, str(e))
