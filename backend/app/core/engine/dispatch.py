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
from enum import Enum
from typing import Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.event.publishers import (
    publish_conversation_created,
    publish_conversation_updated,
)
from app.core.engine.hooks import HookContext, HookEvent, hook_system
from app.core.engine.hooks.schemas import HookMetadata
from app.core.engine.message.category import MessageCategory
from app.core.engine.message.constants import MessageStatus
from app.core.engine.message.reference import reference_service
from app.core.project.utils import get_project_path
from app.infrastructure.database import session_scope
from app.models import Conversation

logger = logging.getLogger(__name__)


class DispatchStatus(str, Enum):
    """Preparation-phase outcome of :class:`DispatchResult`."""

    QUEUED = "queued"
    FAILED = "failed"


@dataclass
class DispatchResult:
    """Result of the synchronous dispatch preparation phase."""

    status: DispatchStatus
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
    metadata = metadata or {}
    # ------------------------------------------------------------------
    # 0. Ensure execution context
    # ------------------------------------------------------------------
    # 多租户 fail-closed：member 身份是按用户隔离（workspace/沙箱/上传）的前提，
    # 缺失先尝试从 thread 的归属会员回填（webhook/resume/宏/子代理等内部入口
    # 只带 thread_id），仍无法确定则拒绝执行——绝不静默落到全局根。
    from app.core.config import settings as _settings

    if _settings.MULTI_TENANT_MODE:
        try:
            mid = int(member_id) if member_id else 0
        except (TypeError, ValueError):
            mid = 0
        if mid <= 0:
            mid = await _member_from_thread(thread_id)
        if mid <= 0:
            raise ValueError(
                "[Dispatch] member identity required in multi-tenant mode "
                f"(thread_id={thread_id}; per-user workspace isolation is mandatory)"
            )
        member_id = mid

    # worker 进程侧恢复身份的唯一通道：BackgroundAgentInputs.metadata["member_id"]
    # （runner_base.build_ctx 从此处读回 ctx.member_id，跨进程内存态丢失）。
    try:
        metadata["member_id"] = int(member_id) if member_id else 0
    except (TypeError, ValueError):
        metadata["member_id"] = 0
    # ------------------------------------------------------------------
    # 0. Resolve model (before creating context)
    # ------------------------------------------------------------------
    active_model = model or ""

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
            # 多租户（云）项目的元数据不在本机，无本地路径是常态而非异常，
            # 降级为 info，避免每个 run 刷 ERROR 噪音。
            # 注意：此处不得使用函数级 `from ... import settings`——那会把
            # settings 变成整个函数的局部变量，后续 212 行等未经过该分支的
            # 代码会抛 UnboundLocalError（顶层已导入，直接用）。
            log_fn = logger.info if settings.MULTI_TENANT_MODE else logger.error
            log_fn(
                f"[Dispatch] No local path for project_id={project_id}"
                + (" (multi-tenant cloud project, expected)" if settings.MULTI_TENANT_MODE else "; refusing to fall back to WORKSPACE_ROOT")
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

    if member_id:
        context.member_id = member_id

    ContextManager.set(context)
    await ContextManager.save(thread_id)

    # ------------------------------------------------------------------
    # 1.6 L0 intent classification via USER_PROMPT_SUBMIT hook
    # ------------------------------------------------------------------
    # The hook computes (or reuses) a high-level intent hint so the downstream
    # hydrator can load context telescopically.  We copy the result into both
    # the EvoContext and the graph inputs metadata.
    context.metadata.prompt = message_content
    context.metadata.source = source
    if metadata.get("intent_hint"):
        context.metadata.intent_hint = metadata["intent_hint"]

    hook_ctx = HookContext(
        thread_id=thread_id,
        run_id=context.request_id,
        project_id=project_id,
        member_id=member_id,
        metadata=HookMetadata(
            prompt=message_content,
            source=source,
            intent_hint=context.metadata.get("intent_hint"),
        ),
    )
    hook_result = await hook_system.trigger(HookEvent.USER_PROMPT_SUBMIT, hook_ctx)
    if hook_result.modified_context:
        context.metadata.intent_hint = hook_result.modified_context.metadata.get(
            "intent_hint"
        ) or context.metadata.get("intent_hint")
    if context.metadata.get("intent_hint"):
        metadata["intent_hint"] = context.metadata.intent_hint

    # ------------------------------------------------------------------
    # 1.5 Handle Upload Session Promotion (Migration from tmp to thread)
    # ------------------------------------------------------------------
    # 多租户：物理根 = member 工作区 uploads/（模块 5）；单用户沿用 CHAT_UPLOAD_DIR。
    from app.core.project.utils import resolve_member_workspace_root

    _upload_base = os.path.join(resolve_member_workspace_root(member_id), "uploads") if (
        settings.MULTI_TENANT_MODE and resolve_member_workspace_root(member_id)
    ) else settings.CHAT_UPLOAD_DIR

    if upload_session_id:
        tmp_dir = os.path.join(_upload_base, f"tmp_{upload_session_id}")
        final_dir = os.path.join(_upload_base, thread_id)

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
            except (OSError, shutil.Error) as e:
                logger.warning(f"[Dispatch] Failed to promote upload session: {e}")

    # ------------------------------------------------------------------
    # 2. Process references (images, files, skills)
    # ------------------------------------------------------------------
    # 【重要】确保在 process_references 之前已经完成了目录转正
    # 这样 reference_service 看到的就是隔离后的最终路径
    upload_root = os.path.join(_upload_base, thread_id)
    if not os.path.exists(upload_root):
        upload_root = os.path.join(_upload_base, "global")

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
    except Exception as e:
        logger.warning(
            f"[Dispatch] Reference service failed: {e}, falling back to raw message_content"
        )
        content_blocks = message_content

    # ------------------------------------------------------------------
    # 2.5 Extract explicit skill_ids from references for downstream routing
    # ------------------------------------------------------------------
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
                # Notify frontends (system channel) so conversation lists
                # refresh in real-time for sessions started from other
                # devices/channels (voice, mobile, wecom, etc.).
                await publish_conversation_created(
                    thread_id=thread_id,
                    project_id=project_id,
                    member_id=member_id,
                    title=conversation.title,
                )
            else:
                conversation.updated_at = datetime.now(timezone.utc)
                # Notify frontends (system channel) so conversation lists
                # refresh in real-time when an existing session is continued
                # from another device/channel (voice, mobile, wecom, etc.).
                await publish_conversation_updated(
                    thread_id=thread_id,
                    project_id=project_id,
                    member_id=member_id,
                    title=conversation.title,
                )

            # New message: persist to DB via Repository to ensure parent_id linkage
            from app.core.engine.message.repository import MessageRepository

            repo = MessageRepository(thread_id, project_id, member_id=member_id)
            msg_id, seq = await repo.persist(
                role="human",
                content=message_content,
                category=MessageCategory.USER,
                is_visible=True,
                references=references_list,
                source=source,
                message_id=message_id,
                session=session,
                # 持久化请求级 metadata（含 host_context），供 Retry 恢复上下文
                metadata=metadata or None,
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
                    category=MessageCategory.USER,
                    status=MessageStatus.COMPLETED,
                    references=references_list,
                    message_id=msg_id,
                    source=source,
                )
                publisher = MessagePublisher(thread_id=thread_id, project_id=project_id)
                # OutputChannelPolicy uses EvoContext.metadata.source to exclude mobile
                # for mobile-source human messages (Gateway already syncs them).
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
        status=DispatchStatus.QUEUED,
        thread_id=thread_id,
        message_id=persisted_msg_id,
        inputs=inputs,
    )


# =============================================================================
# Shared helpers for /resume and /hitl/cancel
# =============================================================================


async def _member_from_thread(thread_id: str) -> int:
    """按 thread 回填归属会员（multi-tenant 下 dispatch 的身份兜底）。"""
    from app.models import Conversation

    try:
        async with session_scope() as session:
            conversation = await session.get(Conversation, thread_id)
            if conversation:
                return int(conversation.member_id or 0)
    except Exception as e:
        logger.warning(
            f"[Dispatch] member from thread {thread_id} lookup failed: {e}",
            exc_info=True,
        )
    return 0


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

        # Notify frontends (system channel) so conversation lists
        # refresh in real-time when a session is continued from
        # another device/channel (voice, mobile, wecom, etc.).
        await publish_conversation_updated(
            thread_id=thread_id,
            project_id=conversation.project_id,
            member_id=conversation.member_id,
            title=conversation.title,
        )

        from app.core.engine.message.repository import MessageRepository

        repo = MessageRepository(
            thread_id,
            project_id if project_id is not None else conversation.project_id,
            member_id=member_id if member_id != 0 else conversation.member_id,
        )
        msg_id, seq = await repo.persist(
            role="human",
            content=content,
            category=MessageCategory.USER,
            is_visible=True,
            message_id=message_id,
            session=session,
        )

        if msg_id:
            from app.core.engine.message.factory import MessageBlockFactory
            from app.core.engine.message.publisher import MessagePublisher

            block = MessageBlockFactory.from_event(
                thread_id=thread_id,
                sequence_number=seq,
                role="human",
                content=content,
                category=MessageCategory.USER,
                status=MessageStatus.COMPLETED,
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
