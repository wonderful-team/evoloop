import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, select, func

from app.api.schemas.conversations import (
    MessageItem,
    ConversationSearchResult,
    RenameRequest,
    ConversationListItem,
    ReferenceItem,
    ChangesetNode,
    RewindResponse,
    ConversationRenameResponse,
    ConversationDeleteResponse,
    RewindRequest,
    MessageListResponse,
    ConversationListResponse,
    ConversationUpdateRequest,
    ConversationUpdateResponse,
)
from app.core.engine.message.folder import MessageNormalizer
from app.core.engine.message.repository import MessageRepository
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.database.sql.database import get_db_session
from app.models import Conversation, FileOperation, Message

logger = logging.getLogger(__name__)

router = APIRouter()


# Message components are now managed via app.core.engine.message.*

@router.get("/", response_model=ConversationListResponse)
async def list_conversations(
    project_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """
    List conversations, optionally filtered by project, with pagination and pinning.
    """
    async with get_db_session() as session:
        # Get total count first
        count_stmt = select(func.count(Conversation.id))
        if project_id is not None:
            count_stmt = count_stmt.where(Conversation.project_id == project_id)
        total_count_result = await session.execute(count_stmt)
        total_count = total_count_result.scalar() or 0

        # Fetch paginated results ordered by pin status and update time
        stmt = select(Conversation).order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc())
        if project_id is not None:
            stmt = stmt.where(Conversation.project_id == project_id)

        # Pagination
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


@router.get("/{thread_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    thread_id: str,
    limit: int = 50,
    before_id: str | None = None,
):
    limit = min(max(limit, 1), 100)
    repo = MessageRepository(thread_id=thread_id)
    all_messages, has_more, total_count = await repo.get_full_history(limit=limit, before_id=before_id, include_invisible=False)

    async with get_db_session() as session:
        # Query file operations: fetch detailed ops for message summary
        file_ops_stmt = (
            select(FileOperation)
            .where(FileOperation.thread_id == thread_id)
        )
        file_ops_result = await session.execute(file_ops_stmt)
        all_file_ops = file_ops_result.scalars().all()
        
        # Map ops to messages
        from collections import defaultdict
        message_ops_map = defaultdict(list)
        for op in all_file_ops:
            message_ops_map[str(op.message_id)].append({
                "path": op.file_path,
                "operation": op.operation.lower()
            })

        # Conversion: Message DB -> MessageBlock (Direct Mapping)
        # Use MessageNormalizer which delegates to MessageBlockFactory
        final_blocks = MessageNormalizer.normalize(all_messages)

        final_items = []
        for block in final_blocks:
            # Map MessageBlock to MessageItem (ensuring extra fields are set)
            item = MessageItem(**block.model_dump())

            # Remove raw tool_calls for SSE/UI (frontend uses steps)
            item.tool_calls = None

            # Bandwidth optimization for tool messages
            if item.role == "tool":
                item.content = ""

            final_items.append(item)

        # Build response with cursors (based on filtered final_items)
        first_id = str(final_items[0].id) if final_items else None
        last_id = str(final_items[-1].id) if final_items else None

        return MessageListResponse(
            data=final_items,
            has_more=has_more,
            first_id=first_id,
            last_id=last_id,
            total_count=total_count,
        )


@router.get("/search", response_model=list[ConversationSearchResult])
async def search_conversations(q: str, project_id: int | None = None):
    if not q or len(q.strip()) < 2:
        return []

    async with get_db_session() as session:
        # Only search visible messages
        # This includes: user, assistant_response, assistant_tool_call, tool_output
        # This excludes: internal_*, error
        #
        # TODO: Replace ilike with proper full-text search (PostgreSQL tsvector
        # or SQLite FTS5) to avoid O(n) sequential scan on large message tables.
        # The leading wildcard prevents index usage on the content column.
        stmt = (
            select(Message)
            .where(Message.content.ilike(f"%{q}%"))
            .where(Message.is_visible == True)
        )

        if project_id is not None:
            stmt = stmt.where(Message.project_id == project_id)

        stmt = stmt.order_by(Message.created_at.desc()).limit(20)

        result = await session.execute(stmt)
        logs = result.scalars().all()

        return [
            ConversationSearchResult(
                id=log.id,
                thread_id=log.thread_id,
                role=log.role,
                content=log.content,
                created_at=str(log.created_at),
                match_snippet=log.content[:200],
            )
            for log in logs
        ]


@router.patch("/{thread_id}", response_model=ConversationUpdateResponse)
async def update_conversation(thread_id: str, req: ConversationUpdateRequest):
    async with get_db_session() as session:
        conversation = await session.get(Conversation, thread_id)
        if not conversation:
            raise HTTPException(404, "Conversation not found")

        if req.title is not None:
            conversation.title = req.title
        if req.is_pinned is not None:
            conversation.is_pinned = req.is_pinned

        # Fetch updated values to return
        title = conversation.title
        is_pinned = conversation.is_pinned

    return ConversationUpdateResponse(
        status="updated",
        thread_id=thread_id,
        title=title,
        is_pinned=is_pinned,
    )


@router.get("/{thread_id}/activity")
async def get_thread_activity(thread_id: str):
    return await activity_monitor.get_activity(thread_id)


@router.delete("/{thread_id}")
async def delete_conversation(thread_id: str):
    from app.infrastructure.database.resource_manager import db_resource_manager
    try:
        # 1. Delete Checkpoints via Checkpointer API (supports both Postgres and SQLite)
        checkpointer = db_resource_manager.checkpointer
        if checkpointer:
            try:
                await checkpointer.adelete_thread(thread_id)
                logger.info(f"[DeleteConversation] Deleted checkpoints for thread {thread_id}")
            except Exception as e:
                # Log but don't fail if checkpoint deletion fails
                logger.warning(f"[DeleteConversation] Failed to delete checkpoints via checkpointer: {e}")

        # 2. Delete Thread Metadata & Logs
        async with get_db_session() as session:
            # Delete Conversation
            conversation = await session.get(Conversation, thread_id)
            if conversation:
                await session.delete(conversation)

            # Delete Logs (Bulk delete)
            await session.execute(delete(Message).where(Message.thread_id == thread_id))

        return ConversationDeleteResponse(status="deleted", thread_id=thread_id)
    except Exception as e:
        logger.error(f"Failed to delete conversation: {e}")
        raise HTTPException(500, str(e))


@router.post("/{thread_id}/rewind", response_model=RewindResponse)
async def rewind_conversation(
    thread_id: str, 
    req: RewindRequest = RewindRequest(),
    request: Request = None
):
    from app.core.engine.rewind import RewindOrchestrator
    from app.core.engine.schemas import RewindOperation as RewindReq
    from app.core.engine.rewind.exceptions import MessageNotFoundError, NoHumanMessageError
    from app.core.events import system_bus

    # Create orchestrator on-demand (stateless, lightweight)
    orchestrator = RewindOrchestrator(event_bus=system_bus)

    try:
        # Create rewind request
        rewind_req = RewindReq(
            thread_id=thread_id,
            target_message_id=req.message_id,
            include_target=True,
            revert_files=req.revert_files,
            reset_state=False,  # Standard rewind doesn't reset state
            reason="user_rewind"
        )
        
        # Perform rewind using new orchestrator
        result = await orchestrator.perform_rewind(
            thread_id=rewind_req.thread_id,
            target_message_id=rewind_req.target_message_id,
            include_target=rewind_req.include_target,
            revert_files=rewind_req.revert_files,
            reset_state=rewind_req.reset_state,
            reason=rewind_req.reason
        )

        # Map new result format to API response
        if result.status == "empty":
            return RewindResponse(status="empty", thread_id=thread_id)
        if result.status == "no_human_message_found":
            return RewindResponse(
                status="no_human_message_found", 
                thread_id=thread_id, 
                removed_count=0
            )

        return RewindResponse(
            status="rewound",
            removed_count=result.removed_message_count,
            thread_id=thread_id,
            files_reverted=result.reverted_file_count,
        )
        
    except MessageNotFoundError:
        raise HTTPException(404, "Target message not found")
    except NoHumanMessageError:
        return RewindResponse(
            status="no_human_message_found",
            thread_id=thread_id,
            removed_count=0
        )
    except Exception as e:
        logger.error(f"Rewind failed: {e}")
        raise HTTPException(500, str(e))


@router.get("/{thread_id}/changeset", response_model=list[ChangesetNode])
async def get_thread_changeset(thread_id: str):
    async with get_db_session() as session:
        stmt = (
            select(FileOperation)
            .where(FileOperation.thread_id == thread_id)
            .order_by(FileOperation.created_at.asc())
        )
        result = await session.execute(stmt)
        ops = result.scalars().all()

        if not ops:
            return []

        # 1. Aggregate operations by file path (Cumulative)
        aggregated = {}  # path -> {operation, diff}
        for op in ops:
            if op.file_path not in aggregated:
                aggregated[op.file_path] = {"operation": op.operation, "diff": op.diff_content}
            else:
                current = aggregated[op.file_path]

                # If it was ADD, keep it as ADD even if followed by EDIT
                if current["operation"] == "ADD" and op.operation == "EDIT":
                    pass # Keep ADD
                else:
                    current["operation"] = op.operation

                # For now, we show the latest diff as the cumulative view is complex without original snapshots
                current["diff"] = op.diff_content

        # 2. Build Tree structure
        root_nodes = []
        path_map = {} # path -> node

        def get_or_create_node(full_path: str, is_dir: bool):
            if full_path in path_map:
                return path_map[full_path]

            parts = full_path.strip("/").split("/")
            name = parts[-1]
            parent_path = "/".join(parts[:-1])

            node = ChangesetNode(
                name=name,
                path=full_path,
                is_dir=is_dir,
                children=[]
            )
            path_map[full_path] = node

            if not parent_path:
                root_nodes.append(node)
            else:
                parent_node = get_or_create_node(parent_path, True)
                parent_node.children.append(node)

            return node

        for path, info in aggregated.items():
            node = get_or_create_node(path, False)
            node.operation = info["operation"]
            node.diff = info["diff"]

        return root_nodes
