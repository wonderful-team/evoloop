"""
Unified Agent Dispatch Layer
==============================

Entry point for all user message flows (HTTP /chat, WebSocket remote commands,
webhooks, etc.). Decoupled from FastAPI — no BackgroundTasks, no HTTPException.

Responsibilities:
1. Reference processing (images, files, skills)
2. DB persistence (Conversation + Message + MessageReference)
3. EvoCloud log sync
4. BackgroundAgentInputs construction (with model fallback)
5. Context setup

Callers are responsible for starting the background task:
- HTTP: bg_tasks.add_task(run_agent_background, thread_id, result.inputs)
- WebSocket: asyncio.create_task(run_agent_background(thread_id, result.inputs))
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.context.manager import ContextManager, EvoContext
from app.core.evocloud import evocloud_manager
from app.domain.project.reference_service import reference_service
from app.infrastructure.database.sql.database import session_scope
from app.models import Conversation, Message, MessageReference

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    """Result of the synchronous dispatch preparation phase."""

    status: str                       # "queued" | "failed"
    thread_id: str
    message_id: int | None = None     # DB persisted message id
    inputs: dict[str, Any] | None = None
    error: str | None = None


async def dispatch_agent_run(
    thread_id: str,
    message_content: str,
    *,
    project_id: int = 1,
    attachments: list[dict[str, Any]] | None = None,
    command_id: int | None = None,
    checkpoint_id: str | None = None,
    model: str | None = None,
    is_retry: bool = False,
    goal_prefix: str = "",
    skip_message_persistence: bool = False,
    context: EvoContext | None = None,
    metadata: dict[str, Any] | None = None,
) -> DispatchResult:
    """
    Unified dispatch preparation for an Agent run.

    This function performs all *synchronous* preparation work.
    It does **not** start the background task — callers must do that themselves.

    Model must be explicitly provided or available in EvoContext.
    """
    # ------------------------------------------------------------------
    # 0. Ensure execution context
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # 0. Resolve model (before creating context)
    # ------------------------------------------------------------------
    active_model = model
    if not active_model:
        from app.infrastructure.config.service import SystemConfigService
        active_model = SystemConfigService.get_value("LLM_MODEL")
        if active_model:
            logger.info(f"[Dispatch] No model specified, using default model: {active_model}")
        else:
            raise ValueError(
                "No model specified and no LLM_MODEL configured in SystemConfigService. "
                "Please provide a model explicitly or configure LLM in system settings."
            )

    # ------------------------------------------------------------------
    # 1. Resolve Environment (Project Path)
    # ------------------------------------------------------------------
    working_directory = None
    if project_id and project_id != 0:
        try:
            project = await evocloud_manager.get_project_by_id(project_id)
            if project and project.get("path"):
                working_directory = project["path"]
                logger.info(f"[Dispatch] Resolved project {project_id} path: {working_directory}")
        except Exception as e:
            logger.warning(f"[Dispatch] Failed to resolve project path for {project_id}: {e}")

    # If not resolved via project, fall back to thread context store (for global mode or manual overrides)
    if not working_directory:
        from app.core.context.thread_store import thread_context_store
        working_directory = thread_context_store.get_working_directory(thread_id)

    if context is None:
        context = EvoContext(
            thread_id=thread_id,
            project_id=project_id,
            command_id=command_id,
            active_model=active_model,
            working_directory=working_directory,
        )
    else:
        # Ensure active_model and working_directory are synchronized
        update_data = {"active_model": active_model}
        if working_directory:
            update_data["working_directory"] = working_directory
        context = context.model_copy(update=update_data)
    
    ContextManager.set(context)
    await ContextManager.save(thread_id)

    # ------------------------------------------------------------------
    # 2. Process references (images, files, skills)
    # ------------------------------------------------------------------
    try:
        async with session_scope() as session:
            ref_context = await reference_service.process_references(
                message_text=message_content,
                attachments=attachments or [],
                session=session,
                project_id=project_id,
            )
        content_blocks = ref_context.content_blocks
    except Exception as e:
        logger.error(f"[Dispatch] Reference processing failed: {e}")
        # Non-fatal: fall back to plain text
        content_blocks = message_content

    # ------------------------------------------------------------------
    # 2.5 Extract explicit skill_id from attachments for downstream routing
    # ------------------------------------------------------------------
    metadata = metadata or {}
    for att in (attachments or []):
        if att.get("type") == "skill":
            skill_meta = att.get("metadata", {})
            metadata["explicit_skill_id"] = skill_meta.get("skill_id")
            metadata["explicit_skill_name"] = skill_meta.get("skill_name")
            logger.info(f"[Dispatch] Explicit skill attached: {metadata['explicit_skill_name']} (ID: {metadata['explicit_skill_id']})")
            break

    # ------------------------------------------------------------------
    # 3. Build goal for activity monitor
    # ------------------------------------------------------------------
    goal = message_content[:200] + "..." if len(message_content) > 200 else message_content
    if attachments:
        goal = f"[Image] {goal}"
    if goal_prefix:
        goal = f"{goal_prefix}{goal}"

    # ------------------------------------------------------------------
    # 4. DB persistence & EvoCloud sync
    # ------------------------------------------------------------------
    persisted_msg_id: int | None = None

    try:
        async with session_scope() as session:
            # Upsert Conversation
            conversation = await session.get(Conversation, thread_id)
            logger.info(
                f"[Dispatch][DIAG] session.get(Conversation, {thread_id!r}) returned: "
                f"{conversation!r} (type={type(conversation).__name__})"
            )
            if not conversation:
                conversation = Conversation(
                    id=thread_id,
                    project_id=project_id,
                    title=message_content[:50],
                )
                session.add(conversation)
                logger.info(
                    f"[Dispatch][DIAG] Adding new Conversation: id={thread_id!r}, "
                    f"project_id={project_id}, title={message_content[:50]!r}"
                )
            else:
                conversation.updated_at = datetime.now(timezone.utc)
                logger.info(
                    f"[Dispatch][DIAG] Found existing Conversation: id={conversation.id!r}, "
                    f"project_id={conversation.project_id}, updated_at will be refreshed"
                )

            if not skip_message_persistence:
                # New message: persist to DB
                from sqlalchemy import func, select

                stmt = select(func.max(Message.sequence_number)).where(Message.thread_id == thread_id)
                max_seq = (await session.execute(stmt)).scalar() or 0

                user_msg = Message(
                    thread_id=thread_id,
                    project_id=project_id,
                    role="human",
                    content=message_content,
                    thinking=None,
                    sequence_number=max_seq + 1,
                )
                session.add(user_msg)
                await session.flush()
                persisted_msg_id = user_msg.id

                logger.info(f"[Dispatch] Persisted user message for {thread_id} (seq={user_msg.sequence_number})")

                # Persist references
                if attachments:
                    for att in attachments:
                        ref_type = att.get("type", "file")
                        target_id = att.get("url") or att.get("id") or "unknown"
                        target_name = att.get("name") or target_id
                        metadata = att.get("metadata")

                        ref = MessageReference(
                            id=str(uuid.uuid4()),
                            message_id=user_msg.id,
                            type=ref_type,
                            target_id=str(target_id),
                            target_name=str(target_name),
                            metadata=metadata,
                        )
                        session.add(ref)

                    logger.info(f"[Dispatch] Persisted {len(attachments)} references for msg {user_msg.id}")
            else:
                logger.info("[Dispatch] Skipped persistence for retry")

    except Exception as e:
        logger.error(
            f"[Dispatch][DIAG] Failed to persist for thread_id={thread_id!r}: "
            f"{type(e).__name__}: {e}",
            exc_info=True,
        )
        return DispatchResult(
            status="failed",
            thread_id=thread_id,
            error=f"Failed to save message: {e}",
        )

    # ------------------------------------------------------------------
    # 5. Build BackgroundAgentInputs
    # ------------------------------------------------------------------
    messages = [{"type": "human", "content": content_blocks}]
    inputs = {
        "messages": messages,
        "project_id": project_id,
        "command_id": str(command_id) if command_id else None,
        "checkpoint_id": checkpoint_id,
        "is_retry": is_retry,
        "goal": goal,
        "session_goal": message_content.strip(),
        "model": active_model,
        "working_directory": working_directory,
        "metadata": metadata or {},
    }

    return DispatchResult(
        status="queued",
        thread_id=thread_id,
        message_id=persisted_msg_id,
        inputs=inputs,
    )


# =============================================================================
# Shared helpers for /resume and /hitl/cancel
# =============================================================================

async def persist_user_message(
    thread_id: str,
    content: str,
    *,
    project_id: int | None = None,
    command_id: int | None = None,
) -> int | None:
    """
    Persist a user message to DB and sync to EvoCloud.

    Used by /chat, /retry, /resume.  Non-blocking on EvoCloud sync errors.
    Returns the persisted ``Message.id``, or ``None`` if the conversation
    does not exist (caller decides whether to treat this as fatal).
    """
    try:
        async with session_scope() as session:
            conversation = await session.get(Conversation, thread_id)
            if not conversation:
                logger.warning(
                    f"[Dispatch] Cannot persist message: conversation {thread_id} not found"
                )
                return None

            conversation.updated_at = datetime.now(timezone.utc)

            from sqlalchemy import func, select

            stmt = select(func.max(Message.sequence_number)).where(Message.thread_id == thread_id)
            max_seq = (await session.execute(stmt)).scalar() or 0

            user_msg = Message(
                thread_id=thread_id,
                project_id=project_id or conversation.project_id,
                role="human",
                content=content,
                sequence_number=max_seq + 1,
            )
            session.add(user_msg)
            await session.flush()

            logger.info(
                f"[Dispatch] Persisted user message for {thread_id} "
                f"(seq={user_msg.sequence_number})"
            )
            return user_msg.id

    except Exception as e:
        logger.error(f"[Dispatch] Failed to persist user message: {e}")
        return None
