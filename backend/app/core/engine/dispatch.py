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
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.message.reference import reference_service
from app.core.project.utils import get_project_path
from app.infrastructure.database import session_scope
from app.models import Conversation

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    """Result of the synchronous dispatch preparation phase."""

    status: str  # "queued" | "failed"
    thread_id: str
    message_id: str | None = None  # DB persisted message id (UUID)
    inputs: dict[str, Any] | None = None
    error: str | None = None


async def dispatch_agent_run(
    thread_id: str,
    message_content: str,
    *,
    project_id: int = DEFAULT_PROJECT_ID,
    references: list[dict[str, Any]] | None = None,
    upload_session_id: str | None = None,
    command_id: int | None = None,
    checkpoint_id: str | None = None,
    model: str | None = None,
    is_retry: bool = False,
    skip_message_persistence: bool = False,
    context: EvoContext | None = None,
    metadata: dict[str, Any] | None = None,
    member_id: int = 0,
    source: str | None = None,
    message_id: str | None = None,
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
            logger.info(
                f"[Dispatch] No model specified, using default model: {active_model}"
            )
        else:
            raise ValueError(
                "No model specified and no LLM_MODEL configured in SystemConfigService. "
                "Please provide a model explicitly or configure LLM in system settings."
            )

    # ------------------------------------------------------------------
    # 1. Prepare minimal Context (working_dir will be hydrated later via events)
    # ------------------------------------------------------------------
    from app.core.context.thread_store import thread_context_store

    current_active_proj = thread_context_store.get_active_project(thread_id)
    working_directory = thread_context_store._thread_contexts.get(thread_id)
    if project_id and (not working_directory or current_active_proj != project_id):
        thread_context_store.set_active_project(thread_id, project_id)
        project_path = await get_project_path(project_id)
        if project_path:
            working_directory = project_path
            thread_context_store.set_working_directory(thread_id, project_path)
        elif project_id != DEFAULT_PROJECT_ID:
            # Project mode but path cannot be resolved: do NOT fall back to
            # WORKSPACE_ROOT or default_root. This prevents the agent from
            # operating on the wrong directory.
            logger.error(
                f"[Dispatch] Failed to resolve local path for project_id={project_id}; "
                "refusing to fall back to WORKSPACE_ROOT"
            )
    if not working_directory:
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
        context.active_model = active_model
        if working_directory:
            context.working_directory = working_directory

    ContextManager.set(context)
    await ContextManager.save(thread_id)

    # ------------------------------------------------------------------
    # 1.5 Handle Upload Session Promotion (Migration from tmp to thread)
    # ------------------------------------------------------------------
    if upload_session_id:
        tmp_dir = os.path.join(settings.CHAT_UPLOAD_DIR, f"tmp_{upload_session_id}")
        final_dir = os.path.join(settings.CHAT_UPLOAD_DIR, thread_id)

        if os.path.exists(tmp_dir) and os.path.isdir(tmp_dir):
            try:
                # If final_dir already exists (multi-upload), merge contents
                if os.path.exists(final_dir):
                    for item in os.listdir(tmp_dir):
                        shutil.move(
                            os.path.join(tmp_dir, item), os.path.join(final_dir, item)
                        )
                    shutil.rmtree(tmp_dir)
                else:
                    os.rename(tmp_dir, final_dir)
                logger.info(
                    f"[Dispatch] Upload session {upload_session_id} promoted to thread {thread_id}"
                )
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"[Dispatch] Failed to promote upload session: {e}")

    # ------------------------------------------------------------------
    # 2. Process references (images, files, skills)
    # ------------------------------------------------------------------
    # 【重要】确保在 process_references 之前已经完成了目录转正
    # 这样 reference_service 看到的就是隔离后的最终路径
    upload_root = os.path.join(settings.CHAT_UPLOAD_DIR, thread_id)
    if not os.path.exists(upload_root):
        upload_root = os.path.join(settings.CHAT_UPLOAD_DIR, "global")

    combined_refs = references or []
    references_list = []
    try:
        async with session_scope() as session:
            ref_context = await reference_service.process_references(
                message_text=message_content,
                references_input=combined_refs,
                session=session,
                root_path=upload_root,  # 使用隔离后的目录作为根
                project_id=project_id,  # 传入项目 ID 以保持 URL 一致性
            )
        content_blocks = ref_context.content_blocks
        references_list = ref_context.references
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"[Dispatch] Reference service failed: {e}, falling back to raw message_content")
        content_blocks = message_content

    # ------------------------------------------------------------------
    # 2.5 Extract explicit skill_ids from references for downstream routing
    # ------------------------------------------------------------------
    metadata = metadata or {}
    explicit_skills = []
    for att in combined_refs:
        if att.get("type") == "skill":
            skill_meta = att.get("metadata") or att.get("meta_data") or {}
            sid = skill_meta.get("skill_id") or att.get("id")
            sname = skill_meta.get("skill_name") or att.get("target_name") or "Unknown"
            if sid:
                explicit_skills.append(
                    {
                        "id": sid,
                        "name": sname,
                        "description": skill_meta.get("description", ""),
                    }
                )
    if explicit_skills:
        metadata["explicit_skills"] = explicit_skills
        logger.info(
            f"[Dispatch] Explicit skills attached: {[s['name'] for s in explicit_skills]} (IDs: {[s['id'] for s in explicit_skills]})"
        )

    # ------------------------------------------------------------------
    # 3. Build goal for activity monitor and session tracking
    # ------------------------------------------------------------------
    from app.core.engine.message.goal_distiller import GoalDistiller

    # Authoritative session_goal (full or long-truncated)
    session_goal = GoalDistiller.from_explicit(message_content)
    # Display-optimized goal for activity monitor (shorter)
    display_goal = GoalDistiller.for_display(session_goal)

    has_images = references and any(ref.get("type") == "image" for ref in references)
    if has_images:
        display_goal = f"[Image] {display_goal}"

    goal_prefix = (metadata or {}).pop("goal_prefix", "")
    if goal_prefix:
        display_goal = f"{goal_prefix}{display_goal}"

    # ------------------------------------------------------------------
    # 4. DB persistence & EvoCloud sync
    # ------------------------------------------------------------------
    persisted_msg_id: str | None = None
    async with session_scope() as session:
        if not skip_message_persistence:
            # Upsert Conversation (only for interactive sessions that persist messages)
            conversation = await session.get(Conversation, thread_id)
            if not conversation:
                first_line = (
                    message_content.strip().split("\n")[0] if message_content else ""
                )
                conversation = Conversation(
                    id=thread_id,
                    project_id=project_id,
                    member_id=member_id,
                    title=first_line[:200] or "未知话题",
                )
                session.add(conversation)
            else:
                conversation.updated_at = datetime.now(timezone.utc)

            # New message: persist to DB via Repository to ensure parent_id linkage
            from app.core.engine.message.repository import MessageRepository

            repo = MessageRepository(thread_id, project_id, member_id=member_id)
            msg_id, seq = await repo.persist(
                role="human",
                content=message_content,
                category="user",
                is_visible=True,
                references=references_list,
                source=source,
                message_id=message_id,
            )
            persisted_msg_id = msg_id

            if msg_id:
                from app.core.engine.message.factory import MessageBlockFactory
                from app.core.engine.message.publisher import MessagePublisher

                block = MessageBlockFactory.from_event(
                    thread_id=thread_id,
                    sequence_number=seq,
                    role="human",
                    content=message_content,
                    category="user",
                    status="completed",
                    references=references_list,
                    message_id=msg_id,
                    source=source,
                )
                publisher = MessagePublisher(thread_id=thread_id, project_id=project_id)
                # Mobile 来源的 human 消息已由 Gateway 直接同步到 MC，
                # Desktop Agent 侧不再通过 message.sync 回写，避免重复。
                if source == "mobile":
                    await publisher.publish(block, channels={"sse"})
                else:
                    await publisher.publish(block)

    # ------------------------------------------------------------------
    # 5. Build BackgroundAgentInputs
    # ------------------------------------------------------------------
    messages = [{"type": "human", "content": content_blocks}]
    inputs = {
        "messages": messages,
        "project_id": project_id,
        "command_id": command_id,
        "checkpoint_id": checkpoint_id,
        "is_retry": is_retry,
        "goal": display_goal,
        "session_goal": session_goal,
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
    member_id: int = 0,
    message_id: str | None = None,
) -> str | None:
    """
    Persist a user message to DB and sync to EvoCloud.

    Used by /chat, /retry, /resume.  Non-blocking on EvoCloud sync errors.
    Returns the persisted ``Message.id``, or ``None`` if the conversation
    does not exist (caller decides whether to treat this as fatal).
    """
    async with session_scope() as session:
        conversation = await session.get(Conversation, thread_id)
        if not conversation:
            logger.warning(
                f"[Dispatch] Cannot persist message: conversation {thread_id} not found"
            )
            return None

        conversation.updated_at = datetime.now(timezone.utc)

        from app.core.engine.message.repository import MessageRepository

        repo = MessageRepository(
            thread_id,
            project_id if project_id is not None else conversation.project_id,
            member_id=member_id if member_id != 0 else conversation.member_id,
        )
        msg_id, seq = await repo.persist(
            role="human",
            content=content,
            category="user",
            is_visible=True,
            message_id=message_id,
        )

        if msg_id:
            from app.core.engine.message.factory import MessageBlockFactory
            from app.core.engine.message.publisher import MessagePublisher

            block = MessageBlockFactory.from_event(
                thread_id=thread_id,
                sequence_number=seq,
                role="human",
                content=content,
                category="user",
                status="completed",
                message_id=msg_id,
            )
            resolved_project_id = (
                project_id if project_id is not None else conversation.project_id
            )
            publisher = MessagePublisher(
                thread_id=thread_id, project_id=resolved_project_id
            )
            await publisher.publish(block)

        return msg_id
