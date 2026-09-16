import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.api.deps import CurrentUserOptional
from app.api.schemas.conversations import (
    ChangesetNode,
    ConversationSearchResult,
    MessageItem,
    MessageListResponse,
    RewindRequest,
    RewindResponse,
)
from app.core.engine.message.folder import MessageNormalizer
from app.core.engine.message.repository import MessageRepository
from app.infrastructure.database import session_scope
from app.models import FileOperation, Message

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/{thread_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    thread_id: str,
    limit: int = 50,
    before_id: str | None = None,
    include_tool_calls: bool = False,
):
    limit = min(max(limit, 1), 100)
    repo = MessageRepository(thread_id=thread_id)
    all_messages, has_more, total_count = await repo.get_full_history(
        limit=limit, before_id=before_id, include_invisible=False
    )

    async with session_scope() as session:
        file_ops_stmt = select(FileOperation).where(FileOperation.thread_id == thread_id)
        file_ops_result = await session.execute(file_ops_stmt)
        all_file_ops = file_ops_result.scalars().all()

        message_ops_map = defaultdict(list)
        for op in all_file_ops:
            message_ops_map[str(op.message_id)].append({
                "path": op.file_path,
                "operation": op.operation.lower()
            })

        final_blocks = MessageNormalizer.normalize(all_messages)

        final_items = []
        for block in final_blocks:
            fields = {f: getattr(block, f) for f in block.model_fields}
            # MessageItem.references 是 ReferenceItem 列表，与 MessageBlock 的
            # MessageReference 非同构模型，直接透传对象会校验失败；序列化为 dict 后
            # ReferenceItem 可正确解析（等价于原 block.model_dump() 行为）。
            references = fields.get("references")
            if references:
                fields["references"] = [
                    r.model_dump() if hasattr(r, "model_dump") else r
                    for r in references
                ]
            item = MessageItem(**fields)
            if not include_tool_calls:
                # 默认不向客户端暴露工具内部调用（工具参数可能含敏感信息）
                item.tool_calls = None
            if item.role == "tool":
                item.content = ""
            final_items.append(item)

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

    async with session_scope() as session:
        stmt = (
            select(Message)
            .where(Message.content.ilike(f"%{q}%"))
            .where(Message.is_visible)
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


@router.post("/{thread_id}/rewind", response_model=RewindResponse)
async def rewind_conversation(
    thread_id: str,
    req: RewindRequest = RewindRequest(),
    _request: Request = None
):
    from app.core.engine.rewind import (
        MessageNotFoundError,
        NoHumanMessageError,
        perform_rewind,
    )

    try:
        result = await perform_rewind(
            thread_id=thread_id,
            target_message_id=req.message_id,
            include_target=True,
            revert_files=req.revert_files,
            reset_state=False,
            reason="user_rewind",
        )

        if result.status == "empty":
            return RewindResponse(status="empty", thread_id=thread_id)
        if result.status == "no_human_message_found":
            return RewindResponse(
                status="no_human_message_found",
                thread_id=thread_id,
                removed_count=0
            )
        if result.status == "partial_failure":
            return RewindResponse(
                status="partial_failure",
                removed_count=result.removed_message_count,
                thread_id=thread_id,
                files_reverted=result.reverted_file_count,
                errors=result.errors,
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
        logger.exception(f"Rewind failed: {e}")
        raise HTTPException(500, str(e))


@router.get("/{thread_id}/changeset", response_model=list[ChangesetNode])
async def get_thread_changeset(thread_id: str):
    async with session_scope() as session:
        stmt = (
            select(FileOperation)
            .where(FileOperation.thread_id == thread_id)
            .order_by(FileOperation.created_at.asc())
        )
        result = await session.execute(stmt)
        ops = result.scalars().all()

        if not ops:
            return []

        aggregated = {}
        for op in ops:
            if op.file_path not in aggregated:
                aggregated[op.file_path] = {
                    "operation": op.operation,
                    "diff": op.diff_content,
                }
            else:
                current = aggregated[op.file_path]
                if current["operation"] == "ADD" and op.operation == "EDIT":
                    pass
                else:
                    current["operation"] = op.operation
                current["diff"] = op.diff_content

        root_nodes = []
        path_map = {}

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
