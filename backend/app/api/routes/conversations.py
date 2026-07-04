import asyncio
import logging
import os

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func

from app.api.deps import CurrentUserOptional
from app.api.schemas.conversations import (
    ChangesetNode,
    ConversationDeleteResponse,
    ConversationListItem,
    ConversationListResponse,
    ConversationSearchResult,
    ConversationUpdateRequest,
    ConversationUpdateResponse,
    MessageItem,
    MessageListResponse,
    RewindRequest,
    RewindResponse,
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
    current_user: CurrentUserOptional = None,
):
    """
    List conversations, optionally filtered by project, with pagination and pinning.
    """
    async with get_db_session() as session:
        # Get total count first
        count_stmt = select(func.count(Conversation.id)).where(Conversation.parent_thread_id.is_(None))
        if project_id is not None:
            count_stmt = count_stmt.where(Conversation.project_id == project_id)
        if current_user is not None:
            count_stmt = count_stmt.where(Conversation.member_id == current_user.id)
        total_count_result = await session.execute(count_stmt)
        total_count = total_count_result.scalar() or 0

        # Fetch paginated results ordered by pin status and update time
        stmt = select(Conversation).where(Conversation.parent_thread_id.is_(None)).order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc())
        if project_id is not None:
            stmt = stmt.where(Conversation.project_id == project_id)
        if current_user is not None:
            stmt = stmt.where(Conversation.member_id == current_user.id)

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
async def search_conversations(
    q: str,
    project_id: int | None = None,
    current_user: CurrentUserOptional = None,
):
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
        if current_user is not None:
            stmt = stmt.where(Message.member_id == current_user.id)

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
async def update_conversation(
    thread_id: str,
    req: ConversationUpdateRequest,
    current_user: CurrentUserOptional = None,
):
    async with get_db_session() as session:
        conversation = await session.get(Conversation, thread_id)
        if not conversation:
            raise HTTPException(404, "Conversation not found")

        # Ownership check
        if current_user is not None and conversation.member_id != 0 and conversation.member_id != current_user.id:
            raise HTTPException(403, "Access denied")

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
async def delete_conversation(
    thread_id: str,
    current_user: CurrentUserOptional = None,
):
    try:
        # Ownership check
        if current_user is not None:
            async with get_db_session() as session:
                conversation = await session.get(Conversation, thread_id)
                if conversation and conversation.member_id != 0 and conversation.member_id != current_user.id:
                    raise HTTPException(403, "Access denied")

        # Publish event — each domain subscriber cleans up its own data
        from app.core.engine.event.publishers import publish_conversation_deleted
        await publish_conversation_deleted(thread_id)

        # Delete Conversation (ORM cascade covers messages, plan, references)
        async with get_db_session() as session:
            conversation = await session.get(Conversation, thread_id)
            if conversation:
                await session.delete(conversation)

        return ConversationDeleteResponse(status="deleted", thread_id=thread_id)
    except HTTPException:
        raise
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


# ---------------------------------------------------------------------------
# Terminal API Endpoints
# ---------------------------------------------------------------------------

class TerminalCommandRequest(BaseModel):
    command: str
    project_id: int | None = None


class TerminalInputRequest(BaseModel):
    text: str
    project_id: int | None = None


async def _hydrate_thread_working_directory(thread_id: str, project_id: int | None = None):
    from app.core.context.thread_store import thread_context_store
    from app.core.project.utils import get_project_path
    from app.models import Conversation
    from app.infrastructure.database.sql.database import get_db_session

    if project_id is None:
        project_id = thread_context_store.get_active_project(thread_id)

    if project_id is None:
        async with get_db_session() as db:
            conv = await db.get(Conversation, thread_id)
            if conv and conv.project_id is not None:
                project_id = conv.project_id

    if project_id is not None:
        thread_context_store.set_active_project(thread_id, project_id)
        project_path = await get_project_path(project_id)
        if project_path:
            thread_context_store.set_working_directory(thread_id, project_path)


@router.post("/{thread_id}/terminal/execute")
async def run_terminal_command(thread_id: str, req: TerminalCommandRequest):
    """Start a Shell command in the thread's persistent PTY session.

    The command runs asynchronously.  Output is streamed in real-time via
    SSE (``task_output`` events) using the BackgroundTask infrastructure.
    Returns the ``task_id`` so the client can correlate SSE events.
    """
    from app.core.execution.terminal.manager import terminal_manager
    from app.core.tools.background import task_manager, CreateBackgroundTaskRequest, TaskType
    from app.core.context.manager import ContextManager, EvoContext

    command = req.command.strip()
    if not command:
        raise HTTPException(status_code=422, detail="command must not be empty")

    await _hydrate_thread_working_directory(thread_id, req.project_id)

    task = await task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title=command,
            tool_name="user_terminal",
            thread_id=thread_id,
            metadata={"enable_streaming_output": True},
        )
    )

    async def _run_async():
        await task_manager.start_task(task.task_id)

        # Echo command output prefix synchronously on the async loop before starting blocking execution
        # to ensure fast builtins (like `pwd`) don't complete and remove the task before the echo arrives
        await task_manager.append_output_async(task.task_id, f"\r\n$ {command}\r\n")

        loop = asyncio.get_running_loop()

        def _blocking_run():
            def on_output(text: str):
                loop.call_soon_threadsafe(
                    task_manager.append_output, task.task_id, text
                )

            with ContextManager.use(EvoContext(thread_id=thread_id)):
                _, _, exit_code = terminal_manager.run_command(
                    command, on_output=on_output
                )
            return exit_code
        try:
            exit_code = await loop.run_in_executor(None, _blocking_run)
        except Exception as exc:
            logger.exception(f"[Terminal][{thread_id}] Command execution error")
            await task_manager.fail_task(task.task_id, error=str(exc))
            return

        if exit_code == 0:
            await task_manager.complete_task(task.task_id)
        else:
            await task_manager.fail_task(
                task.task_id, error=f"Exited with code {exit_code}"
            )

    asyncio.create_task(_run_async())
    return {"task_id": task.task_id}


@router.post("/{thread_id}/terminal/input")
async def send_terminal_input(thread_id: str, req: TerminalInputRequest):
    """Write raw bytes to the thread's PTY master fd WITHOUT acquiring the session lock.

    This is intentionally lock-free so it can be called *while* a command is
    running (e.g. to answer an interactive prompt, send Tab for completion,
    or send Ctrl+C '\\x03' to interrupt a running process).
    """
    from app.core.execution.terminal.manager import terminal_manager
    from app.core.context.manager import ContextManager, EvoContext

    await _hydrate_thread_working_directory(thread_id, req.project_id)

    # Look up the existing session for this thread without modifying context
    session = terminal_manager.get_session_for_thread(thread_id)
    if session is None or session.pty is None:
        # Lazily initialise by running through normal context path
        with ContextManager.use(EvoContext(thread_id=thread_id)):
            session = terminal_manager.get_session()
            _ = session.get_pty(thread_id)  # ensure PTY is started

    pty_inst = session.pty
    if pty_inst is None or pty_inst._master_fd == -1:
        raise HTTPException(
            status_code=400,
            detail="Terminal session not initialised for this thread",
        )

    try:
        pty_inst.write_raw(req.text.encode("utf-8", errors="replace"))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"PTY write failed: {exc}") from exc

    return {"status": "ok"}


@router.get("/{thread_id}/tasks/active")
async def get_active_thread_tasks(thread_id: str):
    """Return all non-completed BackgroundTask objects for a thread.

    Includes the last 1000 lines of buffered output per task so the client
    can restore the terminal canvas after a page refresh.
    """
    from app.core.tools.background import task_manager

    tasks = task_manager.get_active_tasks(thread_id=thread_id)
    return [
        {
            "task_id": t.task_id,
            "task_type": t.task_type.value,
            "title": t.title,
            "status": t.status.value,
            "created_at": t.created_at.isoformat(),
            "output": t.get_recent_output(1000),
            "metadata": (
                t.metadata.model_dump()
                if hasattr(t.metadata, "model_dump")
                else dict(t.metadata)
            ),
        }
        for t in tasks
    ]
