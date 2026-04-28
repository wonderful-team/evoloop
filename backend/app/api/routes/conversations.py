import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, select, func
from sqlalchemy.orm import selectinload

from app.api.schemas.conversations import MessageItem, ConversationSearchResult, RenameRequest, ConversationListItem, \
    ReferenceItem, ChangesetNode, RewindResponse, ConversationRenameResponse, ConversationDeleteResponse, RewindRequest, \
    MessageListResponse
from app.core.engine.message.folding import to_base_message, fold_messages
from app.core.engine.message.schemas import HistoryBlock  # noqa: F401  # 标准化 Block 模型
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.database.sql.database import get_db_session
from app.models import Conversation, FileOperation, Message

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Schemas ---


def get_tool_display_name(tool_name: str) -> str | None:
    """Get friendly display name for a tool from registry."""
    from app.core.tools.registry import get_tool_friendly_name
    return get_tool_friendly_name(tool_name, lang="zh")

# ToolStep and FoldedMessage are now imported from app.core.engine.state.history


@router.get("/", response_model=list[ConversationListItem])
async def list_conversations(project_id: int | None = None):
    """
    List conversations, optionally filtered by project.
    """
    async with get_db_session() as session:
        stmt = select(Conversation).order_by(Conversation.updated_at.desc())
        if project_id is not None:
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


@router.get("/{thread_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    thread_id: str,
    limit: int = 50,
    before_id: int | None = None,
):
    """
    Get message history for a thread from the persistent SQL log.
    Supports pagination for infinite scroll.
    
    Query Logic (simplified):
    1. Query all is_visible=True messages (respecting pagination)
    2. Collect run_ids from visible messages
    3. Query is_visible=False messages with the same run_ids
    4. Merge and return
    
    Note: is_visible is completely determined by message category.
    See MessageCategory.get_visible_categories() for details.
    
    Args:
        thread_id: The conversation thread ID
        limit: Number of messages to return (default 50, max 100)
        before_id: Cursor for pagination - load messages before this ID
    
    Returns:
        MessageListResponse with items, has_more flag, and cursors
    """
    limit = min(max(limit, 1), 100)

    async with get_db_session() as session:
        # Step 1: Query visible messages only
        # is_visible is determined by category, see MessageCategory.get_visible_categories()
        visible_stmt = (
            select(Message)
            .where(
                Message.thread_id == thread_id,
                Message.is_visible == True
            )
            .options(selectinload(Message.references))
            .order_by(Message.id.desc())
            .limit(limit + 1)  # Fetch one extra to check has_more
        )

        # Apply cursor pagination
        if before_id is not None:
            visible_stmt = visible_stmt.where(Message.id < before_id)

        result = await session.execute(visible_stmt)
        visible_messages = result.scalars().all()

        # Check if there are more visible messages
        has_more = len(visible_messages) > limit
        if has_more:
            visible_messages = visible_messages[:limit]

        # Reverse to chronological order (oldest first)
        visible_messages = list(reversed(visible_messages))

        # Step 2: Collect all run_ids from visible messages
        run_ids = {m.run_id for m in visible_messages if m.run_id}

        # To prevent losing the active run if it only has intermediate messages so far
        if before_id is None:
            latest_msg_stmt = (
                select(Message.run_id)
                .where(Message.thread_id == thread_id, Message.run_id.is_not(None))
                .order_by(Message.id.desc())
                .limit(1)
            )
            latest_run_id = (await session.execute(latest_msg_stmt)).scalar_one_or_none()
            if latest_run_id:
                run_ids.add(latest_run_id)

        # Step 3: Fetch all invisible messages associated with these runs
        # These are internal messages (internal_tool_call, internal_system, internal_llm_json, error)
        invisible_messages = []
        if run_ids:
            invisible_stmt = (
                select(Message)
                .where(
                    Message.thread_id == thread_id,
                    Message.is_visible == False,
                    Message.run_id.in_(run_ids)
                )
                .options(selectinload(Message.references))
                .order_by(Message.id.asc())  # Chronological order
            )
            invisible_result = await session.execute(invisible_stmt)
            invisible_messages = invisible_result.scalars().all()

        # Step 4: Merge and sort all messages by id
        all_messages = visible_messages + list(invisible_messages)
        all_messages.sort(key=lambda m: m.id)

        # Get total count on first load (when before_id is None)
        total_count = None
        if before_id is None:
            count_stmt = select(func.count(Message.id)).where(
                Message.thread_id == thread_id,
                Message.is_visible == True
            )
            total_count = (await session.execute(count_stmt)).scalar()

        # Query file operations: presence set + changeset count in one query
        file_ops_stmt = (
            select(FileOperation.message_id, func.count(FileOperation.id).label("count"))
            .where(FileOperation.thread_id == thread_id)
            .group_by(FileOperation.message_id)
        )
        file_ops_result = await session.execute(file_ops_stmt)
        file_ops_rows = file_ops_result.all()
        messages_with_files = set(row.message_id for row in file_ops_rows)
        message_changeset_counts = {str(row.message_id): row.count for row in file_ops_rows}

        # Conversion: Message DB -> LangChain BaseMessage -> FoldedMessage
        langchain_messages = []
        for m in all_messages:
            bm = to_base_message(m)
            if bm:
                langchain_messages.append(bm)
            else:
                logger.warning(f"[Conversations] Dropping message with unknown role: id={m.id}, role={m.role}")

        folded = fold_messages(langchain_messages)

        # Map folded results back to API MessageItem with extra metadata
        # We need to map by ID to keep the extra visibility/changeset data
        # Note: LangChain objects used in fold_messages preserve the 'id' attribute
        db_msg_map = {str(m.id): m for m in all_messages}
        final_items = []

        for f in folded:
            db_m = db_msg_map.get(str(f.id))
            if not db_m:
                # Likely a system or generated message not in DB, keep as is
                final_items.append(MessageItem(**f.model_dump()))
                continue

            # Parse References
            refs = (
                [
                    ReferenceItem(
                        id=ref.id,
                        type=ref.type,
                        target_id=ref.target_id,
                        target_name=ref.target_name,
                        metadata=ref.meta_data,
                    )
                    for ref in db_m.references
                ]
                if db_m.references
                else []
            )

            # Convert FoldedMessage steps to tool_blocks for structured display
            tool_blocks = [
                {
                    "id": step.id,
                    "tool_call_id": step.tool_call_id or step.id,
                    "tool": step.tool,
                    "tool_name": step.tool_name,
                    "tool_name_display": step.tool_name_display,
                    "input": step.input,
                    "output": step.output,
                    "status": step.status,
                    "duration_ms": int(step.duration * 1000) if step.duration else None,
                }
                for step in (f.steps or [])
            ] if f.steps else None

            item = MessageItem(
                **f.model_dump(),
                run_id=db_m.run_id,
                parent_id=db_m.parent_id,
                references=refs,
                has_file_operations=bool(
                    db_m.run_id and db_m.run_id in messages_with_files
                ),
                changeset_count=message_changeset_counts.get(db_m.run_id, 0) if db_m.run_id else 0,
                # --- 新增：填充 MessageBlock 对齐字段 ---
                category=db_m.category,
                content_type=db_m.content_type or "text",
                status=db_m.status,
                sequence_number=db_m.sequence_number,
                checkpoint_id=db_m.checkpoint_id,
                is_visible=db_m.is_visible,
                tool_blocks=tool_blocks,
            )
            
            # Remove raw tool_calls (frontend uses folded steps instead)
            # Note: step.output is preserved in full — frontend needs it to display results
            item.tool_calls = None
            final_items.append(item)

        # Build response with cursors (based on visible messages only)
        first_id = visible_messages[0].id if visible_messages else None
        last_id = visible_messages[-1].id if visible_messages else None

        return MessageListResponse(
            data=final_items,
            has_more=has_more,
            first_id=first_id,
            last_id=last_id,
            total_count=total_count,
        )


@router.get("/search", response_model=list[ConversationSearchResult])
async def search_conversations(q: str, project_id: int | None = None):
    """
    Full-text search on message logs.
    
    Only searches visible messages (is_visible=True).
    Internal messages and errors are excluded from search.
    """
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

    return ConversationRenameResponse(status="updated", thread_id=thread_id, title=req.title)


@router.get("/{thread_id}/activity")
async def get_thread_activity(thread_id: str):
    """Get real-time activity/status for a thread run."""
    return await activity_monitor.get_activity(thread_id)


@router.delete("/{thread_id}")
async def delete_conversation(thread_id: str):
    """Delete a conversation history and its checkpoints."""
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
            await session.commit()

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
    """
    Rewind the conversation to the previous state (Undo last step).
    Optionally revert file changes made by the Agent.
    
    Uses the new event-driven RewindOrchestrator for distributed cleanup.
    """
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
    """
    Get the cumulative file changeset for a thread, formatted as a tree.
    """
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
