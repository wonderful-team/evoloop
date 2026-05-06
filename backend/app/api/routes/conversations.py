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
)
from app.core.engine.message.folder import MessageNormalizer
from app.core.engine.message.repository import MessageRepository
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.database.sql.database import get_db_session
from app.models import Conversation, FileOperation, Message

logger = logging.getLogger(__name__)

router = APIRouter()


# Message components are now managed via app.core.engine.message.*

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
        normalized = MessageNormalizer.normalize(all_messages)
        db_msg_map = {str(m.id): m for m in all_messages}
        final_items = []

        for f in normalized:
            db_m = db_msg_map.get(str(f.id))
            if not db_m:
                final_items.append(MessageItem(**f.model_dump()))
                continue

            msg_id_str = str(db_m.id)
            ops = message_ops_map.get(msg_id_str, [])
            
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

            item = MessageItem(
                **f.model_dump(exclude={
                    "status", "run_id", "parent_id", "references",
                    "category", "content_type", "sequence_number",
                    "checkpoint_id", "is_visible"
                }),
                run_id=db_m.run_id,
                parent_id=db_m.parent_id,
                references=refs,
                has_file_operations=len(ops) > 0,
                changeset_count=len(ops),
                changeset_files=ops,
                category=db_m.category,
                content_type=db_m.content_type or "text",
                status=db_m.status,
                sequence_number=db_m.sequence_number,
                checkpoint_id=db_m.checkpoint_id,
                is_visible=db_m.is_visible,
            )
            
            # Remove raw tool_calls (frontend uses folded steps instead)
            item.tool_calls = None
            
            # Tools often have huge output (e.g. file content, search results).
            # The frontend UI only shows the tool_meta.display_name, so we can
            # safely clear the content to save bandwidth and prevent memory bloat.
            if item.role == "tool":
                item.content = ""
                
            final_items.append(item)

        # Build response with cursors
        first_id = str(all_messages[0].id) if all_messages else None
        last_id = str(all_messages[-1].id) if all_messages else None

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


@router.patch("/{thread_id}")
async def rename_conversation(thread_id: str, req: RenameRequest):
    async with get_db_session() as session:
        conversation = await session.get(Conversation, thread_id)
        if not conversation:
            raise HTTPException(404, "Conversation not found")

        conversation.title = req.title
        await session.commit()

    return ConversationRenameResponse(status="updated", thread_id=thread_id, title=req.title)


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
