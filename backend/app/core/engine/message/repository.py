"""
MessageRepository — Database persistence and query operations for messages.

Extracted from MessageHandler to separate persistence concerns from orchestration.
"""

import logging

from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.orm import selectinload

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.sequence import SequenceService
from app.infrastructure.database import session_scope
from app.models import Message, MessageReference
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


class MessageRepository:
    """
    Handles all database operations for messages:
    - INSERT (persistence)
    - SELECT (query tool inputs, history)
    """

    def __init__(self, thread_id: str, project_id: int | None = None, run_id: str | None = None, member_id: int = 0):
        self.thread_id = thread_id
        self.project_id = project_id
        self.run_id = run_id
        self.member_id = member_id

    async def persist(
        self,
        role: str,
        content: str | None,
        thinking: str | None = None,
        tool_calls: list | None = None,
        category: str = "",
        action_type: str = "text",
        status: str = "completed",
        is_visible: bool = True,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        content_type: str = "text",
        metadata: dict | None = None,
        parent_id: str | None = None,
        references: list[dict] | None = None,
        message_id: str | None = None,
        node_source: str | None = None,
        source: str | None = None,
        executor_device_key: str | None = None,
        executor_device_name: str | None = None,
        session=None,
    ) -> tuple[str | None, int]:
        """
        Persist a message to the database.

        Returns:
            (message_id, sequence_number) or (None, 0) on failure
        """
        # Allow empty content for running tool steps (pre-inserted before execution)
        if not content and not thinking and not tool_calls and status != "running":
            logger.warning(f"[MessageRepository] Skipping persist for {role}: no content, thinking, or tool_calls")
            return None, 0

        try:
            if session is not None:
                return await self._persist_with_session(
                    role,
                    content,
                    thinking,
                    tool_calls,
                    category,
                    action_type,
                    status,
                    is_visible,
                    tool_call_id,
                    tool_name,
                    content_type,
                    metadata,
                    parent_id,
                    references,
                    message_id,
                    node_source,
                    source,
                    executor_device_key,
                    executor_device_name,
                    session,
                )

            seq = await SequenceService.next_sequence(self.thread_id)

            # Resolve parent_id if not provided
            effective_parent_id = parent_id
            if not effective_parent_id:
                effective_parent_id = await self.get_last_message_id()

            async with session_scope() as session:
                log = Message(
                    id=message_id or gen_uuid(),
                    thread_id=self.thread_id,
                    project_id=self.project_id,
                    member_id=self.member_id,
                    role=role,
                    content=content or "",
                    thinking=thinking,
                    sequence_number=seq,
                    run_id=self.run_id,
                    status=status,
                    category=category,
                    content_type=content_type,
                    action_type=action_type,
                    is_visible=is_visible,
                    tool_calls=tool_calls,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    meta_data=metadata,
                    node_source=node_source,
                    source=source,
                    parent_id=effective_parent_id,
                    executor_device_key=executor_device_key,
                    executor_device_name=executor_device_name,
                )
                session.add(log)

                if references:
                    for ref_data in references:
                        if isinstance(ref_data, dict):
                            ref_id = ref_data.get("id") or gen_uuid()
                            ref_type = ref_data.get("type") or "file"
                            ref_target_id = ref_data.get("target_id") or ""
                            ref_target_name = ref_data.get("target_name") or "Unnamed Reference"
                            ref_meta = ref_data.get("metadata") or ref_data.get("meta_data") or {}
                        else:
                            ref_id = getattr(ref_data, "id", None) or gen_uuid()
                            ref_type = getattr(ref_data, "type", None) or "file"
                            ref_target_id = getattr(ref_data, "target_id", None) or ""
                            ref_target_name = getattr(ref_data, "target_name", None) or "Unnamed Reference"
                            ref_meta = getattr(ref_data, "metadata", None) or getattr(ref_data, "meta_data", None) or {}

                        ref = MessageReference(
                            id=ref_id,
                            message_id=log.id,
                            type=ref_type,
                            target_id=ref_target_id,
                            target_name=ref_target_name,
                            meta_data=ref_meta,
                        )
                        session.add(ref)

                await session.flush()

            return log.id, seq

        except Exception as e:
            logger.exception(f"[MessageRepository] Failed to persist message: {e}")
            raise

    async def _persist_with_session(
        self,
        role,
        content,
        thinking,
        tool_calls,
        category,
        action_type,
        status,
        is_visible,
        tool_call_id,
        tool_name,
        content_type,
        metadata,
        parent_id,
        references,
        message_id,
        node_source,
        source,
        executor_device_key,
        executor_device_name,
        session,
    ) -> tuple[str | None, int]:
        seq = await SequenceService.next_sequence(self.thread_id, session=session)

        effective_parent_id = parent_id
        if not effective_parent_id:
            effective_parent_id = await self.get_last_message_id(session=session)

        log = Message(
            id=message_id or gen_uuid(),
            thread_id=self.thread_id,
            project_id=self.project_id,
            member_id=self.member_id,
            role=role,
            content=content or "",
            thinking=thinking,
            sequence_number=seq,
            run_id=self.run_id,
            status=status,
            category=category,
            content_type=content_type,
            action_type=action_type,
            is_visible=is_visible,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            meta_data=metadata,
            node_source=node_source,
            source=source,
            parent_id=effective_parent_id,
            executor_device_key=executor_device_key,
            executor_device_name=executor_device_name,
        )
        session.add(log)

        if references:
            for ref_data in references:
                if isinstance(ref_data, dict):
                    ref_id = ref_data.get("id") or gen_uuid()
                    ref_type = ref_data.get("type") or "file"
                    ref_target_id = ref_data.get("target_id") or ""
                    ref_target_name = ref_data.get("target_name") or "Unnamed Reference"
                    ref_meta = ref_data.get("metadata") or ref_data.get("meta_data") or {}
                else:
                    ref_id = getattr(ref_data, "id", None) or gen_uuid()
                    ref_type = getattr(ref_data, "type", None) or "file"
                    ref_target_id = getattr(ref_data, "target_id", None) or ""
                    ref_target_name = getattr(ref_data, "target_name", None) or "Unnamed Reference"
                    ref_meta = getattr(ref_data, "metadata", None) or getattr(ref_data, "meta_data", None) or {}

                ref = MessageReference(
                    id=ref_id,
                    message_id=log.id,
                    type=ref_type,
                    target_id=ref_target_id,
                    target_name=ref_target_name,
                    meta_data=ref_meta,
                )
                session.add(ref)

        await session.flush()
        return log.id, seq

    async def update(self, sequence_number: int, **fields) -> str | None:
        """
        Update an existing message by sequence_number.

        Args:
            sequence_number: The sequence_number of the message to update
            **fields: Fields to update (e.g. status="completed", content="...")

        Returns:
            The message ID (UUID string) if updated, None if message not found
        """
        try:
            async with session_scope() as session:
                from app.models import Message

                stmt = select(Message).where(
                    Message.thread_id == self.thread_id,
                    Message.sequence_number == sequence_number,
                )
                result = await session.execute(stmt)
                msg = result.scalar_one_or_none()
                if not msg:
                    logger.warning(f"[MessageRepository] Message not found for update: thread={self.thread_id}, seq={sequence_number}")
                    return None

                for key, value in fields.items():
                    if key == "content" and value is None:
                        value = ""
                    if hasattr(msg, key):
                        setattr(msg, key, value)
                    else:
                        logger.warning(f"[MessageRepository] Unknown field '{key}' on Message, skipping")

                await session.flush()
                logger.info(f"[MessageRepository] Updated message seq={sequence_number}: {fields.keys()}")
                return msg.id

        except Exception as e:
            logger.exception(f"[MessageRepository] Failed to update message: {e}")
            raise

    async def sync_changeset_reference(
        self,
        message_id: str,
        file_path: str,
        operation: str,
        run_id: str | None = None,
        tool_call_id: str | None = None,
        diff_content: str | None = None,
    ) -> bool:
        """
        同步或创建消息的 changeset 引用。
        支持通过 message_id 或 tool_call_id 定位目标消息。
        """
        try:
            async with session_scope() as session:
                target_msg_id = message_id

                # 1. 如果提供了 tool_call_id，尝试找回准确的消息 ID (解决回调与执行器 ID 不一致问题)
                if tool_call_id:
                    stmt_msg = select(Message.id).where(
                        Message.thread_id == self.thread_id,
                        Message.tool_call_id == tool_call_id
                    ).order_by(desc(Message.sequence_number))
                    res = await session.execute(stmt_msg)
                    found_id = res.scalar_one_or_none()
                    if found_id:
                        target_msg_id = found_id
                        logger.debug(f"[MessageRepository] Resolved tool_call_id {tool_call_id} -> msg {target_msg_id}")

                # 2. 查找是否已有 changeset 引用
                stmt = select(MessageReference).where(
                    MessageReference.message_id == target_msg_id,
                    MessageReference.type == "changeset",
                )
                result = await session.execute(stmt)
                ref = result.scalar_one_or_none()

                new_file_entry = {
                    "path": file_path,
                    "operation": operation.lower(),
                    "diff": diff_content,
                }

                if ref:
                    # 3. 更新现有引用
                    meta = ref.meta_data or {}
                    files = meta.get("files", [])

                    # 去重检查
                    if not any(f["path"] == file_path for f in files):
                        files.append(new_file_entry)
                        meta["files"] = files
                        meta["count"] = len(files)
                        ref.meta_data = meta
                        logger.debug(f"[MessageRepository] Updated changeset for msg {target_msg_id}: added {file_path}")
                else:
                    # 4. 创建新引用 (注意：如果消息不存在，此处仍会触发 IntegrityError)
                    # 我们增加一个存在性检查
                    stmt_check = select(Message.id).where(Message.id == target_msg_id)
                    if not (await session.execute(stmt_check)).scalar_one_or_none():
                        logger.warning(f"[MessageRepository] Cannot sync changeset: Message {target_msg_id} not found in DB yet.")
                        return False

                    ref = MessageReference(
                        id=gen_uuid(),
                        message_id=target_msg_id,
                        type="changeset",
                        target_id=run_id or target_msg_id,
                        target_name="代码变更集",
                        meta_data={
                            "files": [new_file_entry],
                            "count": 1
                        },
                    )
                    session.add(ref)
                    logger.debug(f"[MessageRepository] Created new changeset for msg {target_msg_id} with {file_path}")

                await session.flush()
                return True
        except Exception as e:
            logger.exception(f"[MessageRepository] Failed to sync changeset reference: {e}")
            return False

    async def resolve_tool_input(self, tool_call_id: str | None, tool_name: str | None = None) -> dict:
        """
        Resolve tool input arguments.
        Prioritizes the actual tool message (if pre-inserted by handler),
        falling back to the most recent AI message's tool_calls.
        """
        if not tool_call_id and not tool_name:
            return {}

        try:
            async with session_scope() as session:
                # 1. Try to find the pre-inserted tool message itself first (Best for exact matches)
                if tool_call_id:
                    stmt_tool = (
                        select(Message)
                        .where(Message.thread_id == self.thread_id)
                        .where(Message.role == "tool")
                        .where(Message.tool_call_id == tool_call_id)
                        .order_by(desc(Message.sequence_number))
                        .limit(1)
                    )
                    result_tool = await session.execute(stmt_tool)
                    tool_msg = result_tool.scalar_one_or_none()
                    if tool_msg and tool_msg.meta_data and isinstance(tool_msg.meta_data, dict):
                        input_data = tool_msg.meta_data.get("input")
                        if isinstance(input_data, dict) and input_data:
                            return input_data

                # 2. Fallback: Try matching from AI message tool_calls
                stmt_ai = (
                    select(Message)
                    .where(Message.thread_id == self.thread_id)
                    .where(Message.role == "ai")
                    .where(Message.tool_calls.is_not(None))
                    .order_by(desc(Message.sequence_number))
                    .limit(1)
                )
                result_ai = await session.execute(stmt_ai)
                ai_msg = result_ai.scalar_one_or_none()
                if not ai_msg or not ai_msg.tool_calls:
                    return {}

                from app.core.engine.message.utils import normalize_tool_calls

                tool_calls = normalize_tool_calls(ai_msg.tool_calls)

                for tc in tool_calls:
                    if tc.get("id") == tool_call_id:
                        return tc.get("args") or {}

        except Exception as e:
            logger.exception(f"[MessageRepository] resolve_tool_input failed: {e}")
            raise
        return {}

    async def update_status_by_tool_call_id(self, tool_call_id: str, status: str) -> bool:
        """
        Update message status by tool_call_id (primarily for HITL closure).
        """
        try:
            async with session_scope() as session:
                stmt = (
                    update(Message)
                    .where(Message.thread_id == self.thread_id)
                    .where(Message.tool_call_id == tool_call_id)
                    .values(status=status)
                )
                result = await session.execute(stmt)
                # No flush needed here as update() returns rowcount directly in some dialects,
                # but session.execute with update statement is fine.
                logger.info(f"[MessageRepository] Updated status to {status} for tool_call_id {tool_call_id}")
                return result.rowcount > 0
        except Exception as e:
            logger.exception(f"[MessageRepository] Failed to update status by tool_call_id {tool_call_id}: {e}")
            raise

    async def update_content_by_tool_call_id(self, tool_call_id: str, content: str) -> bool:
        """
        Update message content by tool_call_id (used to deliver async callback
        results, e.g. A2A, back into the tool message the LLM sees).
        """
        try:
            async with session_scope() as session:
                stmt = (
                    update(Message)
                    .where(Message.thread_id == self.thread_id)
                    .where(Message.tool_call_id == tool_call_id)
                    .values(content=content)
                )
                result = await session.execute(stmt)
                logger.info(f"[MessageRepository] Updated content for tool_call_id {tool_call_id}")
                return result.rowcount > 0
        except Exception as e:
            logger.exception(f"[MessageRepository] Failed to update content by tool_call_id {tool_call_id}: {e}")
            raise

    async def get_last_message_id(self, session=None) -> str | None:
        """Get the ID of the most recent message in the thread."""
        try:
            if session is None:
                async with session_scope() as s:
                    return await self._get_last_message_id(s)
            return await self._get_last_message_id(session)
        except Exception as e:
            logger.exception(f"[MessageRepository] Failed to get last message id: {e}")
            return None

    async def _get_last_message_id(self, session) -> str | None:
        stmt = (
            select(Message.id)
            .where(Message.thread_id == self.thread_id)
            .order_by(desc(Message.sequence_number))
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_full_history(
        self,
        limit: int = 50,
        before_id: str | None = None,
        include_invisible: bool = True,
    ) -> tuple[list[Message], bool, int | None]:
        """
        Fetches conversation history.
        If include_invisible is True, fetches both visible and associated invisible messages.
        If False, only fetches visible messages (standard UI history).
        Returns (messages, has_more, total_count).
        """
        async with session_scope() as session:
            # 1. Query visible messages with cursor pagination
            visible_stmt = (
                select(Message)
                .where(
                    Message.thread_id == self.thread_id,
                    Message.is_visible == True,
                    or_(
                        Message.category.is_(None),
                        Message.category != MessageCategory.HITL_REQUEST.value,
                    ),
                )
                .options(selectinload(Message.references))
                .order_by(Message.sequence_number.desc())
                .limit(limit + 1)
            )

            if before_id:
                before_seq = (await session.execute(
                    select(Message.sequence_number).where(Message.id == before_id)
                )).scalar_one_or_none()
                if before_seq:
                    visible_stmt = visible_stmt.where(Message.sequence_number < before_seq)

            result = await session.execute(visible_stmt)
            visible_messages = result.scalars().all()

            has_more = len(visible_messages) > limit
            if has_more:
                visible_messages = visible_messages[:limit]

            # 2. Fetch associated invisible messages for these runs
            run_ids = {m.run_id for m in visible_messages if m.run_id}

            # Special case: include current active run even if its messages are invisible
            if not before_id:
                latest_run_id = (await session.execute(
                    select(Message.run_id)
                    .where(Message.thread_id == self.thread_id, Message.run_id.is_not(None))
                    .order_by(Message.sequence_number.desc())
                    .limit(1)
                )).scalar_one_or_none()
                if latest_run_id:
                    run_ids.add(latest_run_id)

            all_messages = list(visible_messages)
            if include_invisible and run_ids:
                invisible_stmt = (
                    select(Message)
                    .where(
                        Message.thread_id == self.thread_id,
                        Message.is_visible == False,
                        Message.run_id.in_(run_ids),
                    )
                    .options(selectinload(Message.references))
                )
                invisible_messages = (await session.execute(invisible_stmt)).scalars().all()
                all_messages.extend(invisible_messages)

            all_messages.sort(key=lambda m: m.sequence_number or 0)

            # 3. Total count for first load
            total_count = None
            if not before_id:
                total_count = (await session.execute(
                    select(func.count(Message.id)).where(
                        Message.thread_id == self.thread_id,
                        Message.is_visible == True,
                        Message.category != MessageCategory.HITL_REQUEST.value
                    )
                )).scalar()

            return all_messages, has_more, total_count
