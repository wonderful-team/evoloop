import logging
import os
import re
import shutil
import time

from sqlalchemy import func, select, text, desc

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.learning.trace_recorder import sync_thread_to_graph
from app.infrastructure.config import SystemConfigService
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.queue.factory import shared_task
from app.models import FileOperation, Message

logger = logging.getLogger(__name__)


async def _notify_file_operation(thread_id: str, message_id: str, file_path: str, operation: str):
    """Notify frontend of new file operation via SSE through MessagePublisher."""
    from app.core.engine.message.publisher import MessagePublisher
    from app.core.engine.message.schemas import MessageBlock

    block = MessageBlock(
        id=f"file-op-{thread_id}-{message_id}",
        thread_id=thread_id,
        role="system",
        category="file_operation",
        content=f"File {operation}: {file_path}",
        content_type="text",
        status="completed",
        is_visible=False,
        sequence_number=int(time.time() * 1000),
        meta_data={
            "file_path": file_path,
            "operation": operation,
            "message_id": message_id,
        },
    )

    publisher = MessagePublisher(thread_id=thread_id)
    await publisher.publish(block, channels={"sse"})
    logger.debug(f"[Celery] Published file operation event for {file_path}")


async def _persist_file_operation_task(
    thread_id: str,
    message_id: str,
    file_path: str,
    operation: str,
    diff_content: str,
    original_content: str | None = None,
    run_id: str | None = None,
    tool_call_id: str | None = None,
):
    """Internal implementation of file operation persistence."""
    async with session_scope() as session:
        # Determine final message ID (resolve tool_call_id if needed)
        target_msg_id = message_id
        if tool_call_id:
            # Find the actual message ID associated with this tool_call_id
            stmt_msg = select(Message.id).where(
                Message.thread_id == thread_id,
                Message.tool_call_id == tool_call_id
            ).order_by(desc(Message.sequence_number))
            res = await session.execute(stmt_msg)
            found_id = res.scalar_one_or_none()
            if found_id:
                target_msg_id = found_id

        op = FileOperation(
            thread_id=thread_id,
            message_id=target_msg_id,
            run_id=run_id,
            file_path=file_path,
            operation=operation,
            diff_content=diff_content,
            original_content=original_content,
        )
        session.add(op)
        logger.info(f"[Celery] Persisted file operation for {file_path}")

    # --- [Phase 2] 同步到消息标准化引用并触发实时更新 ---
    from app.core.engine.message.repository import MessageRepository
    repo = MessageRepository(thread_id=thread_id)
    await repo.sync_changeset_reference(
        message_id=message_id,
        file_path=file_path,
        operation=operation,
        run_id=run_id,
        tool_call_id=tool_call_id
    )


@shared_task(name="engine_persist_file_operation")
async def persist_file_operation_task(
    thread_id: str,
    message_id: str,
    file_path: str,
    operation: str,
    diff_content: str,
    original_content: str | None = None,
    run_id: str | None = None,
    tool_call_id: str | None = None,
):
    """Background task wrapper."""
    from app.core.engine.message.mapper import BlockMapper
    from app.core.engine.message.publisher import MessagePublisher
    from sqlalchemy.orm import selectinload

    await _persist_file_operation_task(
        thread_id=thread_id,
        message_id=message_id,
        file_path=file_path,
        operation=operation,
        diff_content=diff_content,
        original_content=original_content,
        run_id=run_id,
        tool_call_id=tool_call_id,
    )

    # 2. 触发 SSE 增量更新：让前端气泡即时显示“变更徽章”
    async with session_scope() as session:
        # 获取最新的消息（带引用）
        stmt = select(Message).where(Message.id == message_id).options(selectinload(Message.references))
        result = await session.execute(stmt)
        db_msg = result.scalar_one_or_none()
        
        if db_msg:
            block = BlockMapper.from_db(db_msg)
            publisher = MessagePublisher(thread_id=thread_id)
            # action="update" 会触发前端对应消息的局部刷新
            await publisher.publish(block, action="update", channels={"sse"})

    # 原有的细粒度通知逻辑保留
    await _notify_file_operation(thread_id, message_id, file_path, operation)


@shared_task(name="engine_harvest_concepts")
async def harvest_concepts_task(concepts_data: list[dict], project_id: int):
    """
    Background task to store harvested concepts into the memory system.
    """
    if not concepts_data:
        return

    from app.core.environment.android import android_service
    from app.core.memory.lifespan import MemoryLifespanManager

    logger.info(f"[Celery] Harvesting {len(concepts_data)} concepts...")
    
    # Ensure memory is initialized once per batch
    if not MemoryLifespanManager.is_initialized():
        await MemoryLifespanManager.ainitialize()
    container = MemoryLifespanManager.get_container()

    for c in concepts_data:
        name = c["name"]
        description = c["description"]

        # Optimized logic for Android layouts
        if name.startswith("android_layout:"):
            logger.info(f"Optimizing layout concept: {name}")
            elements, summary = await android_service.dehydrate_layout(description)

            if elements:
                # 1. Trigger App Atlas mapping (Structured Storage)
                pkg_match = re.search(r"\(([^)]+)\)", name)
                bundle_id = pkg_match.group(1) if pkg_match else "unknown"

                from app.core.environment.event.publishers import publish_ui_tree_observed
                await publish_ui_tree_observed(
                    platform="android",
                    bundle_id=bundle_id,
                    window_title=name.replace("android_layout:", "").split('(')[0].strip(),
                    elements=[e.model_dump() for e in elements],
                )

                # 2. Use dehydrated summary as Concept description
                description = summary
                logger.debug(f"Dehydrated {name} into summary: {summary}")

        # Use unified MemoryManager interface
        await container.memory_manager.store_concept(
            concept=name,
            description=description,
            project_id=project_id,
        )
        logger.info(f"Harvested concept: {name}")


@shared_task(name="engine_record_episode")
async def record_episode_task(
    thread_id: str,
    project_id: int,
    goal: str | None = None,
    result_summary: str | None = None,
    concept_names: list[str] | None = None,
    source_message_id: str | None = None,
    auto_synthesize: bool = False,
    model: str | None = None,
):
    """
    Background task to sync thread trace to the episode graph (memory system).
    """
    logger.info(f"[Celery] Recording episode for thread {thread_id} (Source: {source_message_id}, AutoSynth: {auto_synthesize})...")

    ctx = EvoContext(thread_id=thread_id, project_id=project_id, active_model=model)
    token = ContextManager.set(ctx)

    try:
        await sync_thread_to_graph(
            thread_id=thread_id,
            project_id=project_id,
            goal=goal or "No goal specified",
            result_summary=result_summary,
            concept_names=concept_names,
            source_message_id=source_message_id,
        )
        logger.info(f"[Celery] Episode recorded for thread {thread_id}")

        if auto_synthesize:
            from app.core.learning.skill_synthesizer import WorkflowSynthesizer
            from app.models.learning import TraceEvent

            # Check if there are meaningful events to synthesize
            async with session_scope() as db:
                stmt = select(func.count(TraceEvent.id)).where(TraceEvent.thread_id == thread_id)
                count_res = await db.execute(stmt)
                event_count = count_res.scalar()

            if event_count and event_count >= 3: 
                logger.info(f"[Celery] 🧬 Auto-triggering skill synthesis for thread {thread_id} ({event_count} events)")
                synthesizer = WorkflowSynthesizer(thread_id=thread_id)
                result = await synthesizer.synthesize()
                if result:
                    logger.info(f"[Celery] ✅ Skill synthesis complete: {result.name}")
                else:
                    logger.info("[Celery] ⏩ Skill synthesis skipped (no unique pattern found)")
    finally:
        ContextManager.reset(token)


@shared_task(name="engine_prune_checkpoints")
async def prune_checkpoints_task(keep_days: int = 7):
    """
    Background task to prune old LangGraph checkpoints.
    """
    is_sqlite = settings.EMBEDDED_MODE or "sqlite" in settings.SQLALCHEMY_DATABASE_URI

    async with session_scope() as session:
        if is_sqlite:
            # SQLite pruning logic
            await session.execute(text("DELETE FROM writes WHERE thread_id NOT IN (SELECT thread_id FROM checkpoints)"))
            logger.info("[Celery] Pruned orphaned LangGraph 'writes' in SQLite.")
        else:
            # Postgres pruning
            await session.execute(
                text("DELETE FROM checkpoint_writes WHERE timestamp < now() - interval ':days day'"),
                {"days": keep_days}
            )
            await session.execute(text("DELETE FROM checkpoints WHERE thread_id NOT IN (SELECT thread_id FROM checkpoint_writes)"))
            await session.execute(text("DELETE FROM checkpoint_blobs WHERE thread_id NOT IN (SELECT thread_id FROM checkpoints)"))

    logger.info(f"[Celery] Pruned LangGraph checkpoints/writes (Keep: {keep_days} days).")


@shared_task(name="engine_cleanup_artifacts")
def cleanup_artifacts_task(max_age_days: int = 3):
    """
    Background task to cleanup old screenshots and temporary artifacts.
    """
    target_dirs = [settings.SCREENSHOTS_DIR, settings.BROWSER_ARTIFACTS_DIR]
    now = time.time()
    cutoff = now - (max_age_days * 86400)

    for directory in target_dirs:
        if not os.path.exists(directory):
            continue

        logger.info(f"[Celery] Cleaning up old artifacts in {directory}...")
        from app.core.file import FileTraverser
        for entry in FileTraverser.list_entries(directory):
            try:
                # File-level try-except is justified for cleanup tasks
                if os.path.getmtime(entry.path) < cutoff:
                    if entry.is_file():
                        os.remove(entry.path)
                    elif entry.is_dir():
                        shutil.rmtree(entry.path)
            except Exception as e:
                logger.warning(f"Failed to delete artifact {entry.path}: {e}")


@shared_task(name="engine_git_harvest")
async def git_harvest_task(cwd: str, project_id: int, model: str | None = None):
    """
    Background task to extract knowledge concepts from git diff.
    """
    ctx = EvoContext(project_id=project_id, active_model=model)
    token = ContextManager.set(ctx)

    import subprocess
    from app.infrastructure.config.service import SystemConfigService
    from app.models.schemas.git import GitConceptExtractionResult

    try:
        # 1. Get Diff
        if not os.path.exists(cwd):
            logger.warning(f"[Celery] Skipping git harvest: Directory '{cwd}' does not exist.")
            return

        cmd = ["git", "diff", "HEAD"]
        process = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=15)
        diff_text = process.stdout
        if not diff_text.strip():
            return
        
        if len(diff_text) > 10000:
            diff_text = diff_text[:10000] + "\n...(truncated)"

        # 2. Extract
        user_lang = SystemConfigService.get_language_preference()

        from app.utils import render_template
        prompt_text = render_template(
            "core/engine/tasks/git_harvest.prompt.j2",
            diff_content=diff_text,
            user_language=user_lang
        )

        from app.core.llm import InternalLLMService
        model_name = SystemConfigService.get_value("LLM_MODEL")
        result = await InternalLLMService.invoke_structured(
            messages=[{"role": "system", "content": prompt_text}],
            purpose="memory_extraction",
            output_schema=GitConceptExtractionResult,
            temperature=0.0,
            max_tokens=4000,
            model_name=model_name,
        )

        if result.concepts:
            from app.core.memory.lifespan import MemoryLifespanManager
            if not MemoryLifespanManager.is_initialized():
                await MemoryLifespanManager.ainitialize()
            container = MemoryLifespanManager.get_container()
            
            from app.core.memory.schemas import Concept
            for concept in result.concepts:
                mem_concept = Concept(
                    name=concept.name,
                    description=concept.description,
                    project_id=project_id,
                    related_files=concept.related_files
                )
                await container.memory_manager.store_concept(mem_concept)
                logger.info(f"[Celery] Harvested concept: {concept.name}")
    finally:
        ContextManager.reset(token)


@shared_task(name="engine_reconcile_skill_macro")
async def reconcile_skill_macro_task(skill_id: int, thread_id: str, model: str | None = None):
    """
    Background task to reconcile a broken skill macro.
    """
    from app.core.learning.skill_synthesizer import WorkflowSynthesizer
    from app.models.learning import LearnedSkill, TraceEvent

    # Pre-check: ensure there are enough trace events to synthesize from
    async with session_scope() as db:
        stmt = select(func.count(TraceEvent.id)).where(TraceEvent.thread_id == thread_id)
        count_res = await db.execute(stmt)
        event_count = count_res.scalar()

    if not event_count or event_count < 3:
        logger.warning(
            f"[Celery] Skipping skill reconciliation for {thread_id}: "
            f"only {event_count or 0} trace events found (need >= 3)."
        )
        return

    ctx = EvoContext(thread_id=thread_id, active_model=model)
    token = ContextManager.set(ctx)

    try:
        logger.info(f"[Celery] Reconciling Skill {skill_id} from thread {thread_id}...")
        synthesizer = WorkflowSynthesizer(thread_id)
        repaired_skill = await synthesizer.synthesize()

        if not repaired_skill.macro_script:
            logger.warning(f"[Celery] No valid macro synthesized from recovery thread {thread_id}. Aborting patch.")
            return

        async with session_scope() as session:
            stmt = select(LearnedSkill).where(LearnedSkill.id == skill_id)
            result = await session.execute(stmt)
            original_skill = result.scalar_one_or_none()

            if original_skill:
                original_skill.macro_script = repaired_skill.macro_script
                if repaired_skill.instructions:
                    original_skill.instructions = repaired_skill.instructions
                logger.info(f"[Celery] ✅ Skill {skill_id} has been self-healed.")
    finally:
        ContextManager.reset(token)


@shared_task(name="engine_scheduler_tick")
async def engine_scheduler_tick():
    """
    Background task to poll for due autonomous tasks.
    """
    from app.infrastructure.scheduler.service import SchedulerService
    await SchedulerService.tick()


@shared_task(name="run_autonomous_task_execution")
async def run_autonomous_task_execution(task_id: int, project_id: int | None = None):
    """
    Background task to execute an autonomous task.
    """
    from app.core.engine.background_agent import run_agent_background
    from app.core.environment.devices import DevicePool
    from app.models.learning import LearnedSkill
    from app.models.scheduler import AutonomousTask

    # 1. Reserve a device
    device_id = await DevicePool.reserve_device(task_id=f"task-{task_id}")
    if not device_id:
        raise ValueError(f"No available Android devices for task {task_id}.")

    try:
        async with session_scope() as session:
            task = await session.get(AutonomousTask, task_id)
            if not task:
                raise ValueError(f"Autonomous task {task_id} not found.")

            skill = await session.get(LearnedSkill, task.skill_id)
            if not skill:
                raise ValueError(f"Skill {task.skill_id} for task {task_id} not found.")

            intent_description = task.intent_description
            skill_name = skill.name
            skill_id = skill.id

        thread_id = f"auton-{task_id}-{int(time.time())}"

        from app.utils import render_template
        prompt = render_template(
            "core/engine/tasks/autonomous_task.prompt.j2",
            intent_description=intent_description,
            skill_name=skill_name,
            skill_id=skill_id,
            device_id=device_id
        )

        # 2. Trigger Unified Dispatcher
        from app.core.engine.dispatch import dispatch_agent_run
        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=prompt,
            project_id=project_id if project_id is not None else DEFAULT_PROJECT_ID,
            goal_prefix="[Autonomous Task] ",
            metadata={
                "autonomous_task_id": task_id,
                "source_skill_id": skill_id,
                "device_id": device_id  
            }
        )

        if result.status == "failed":
            raise RuntimeError(f"Dispatch failed for task {task_id}: {result.error}")

        logger.info(f"[Celery] Starting autonomous agent for task {task_id} on {device_id}")

        async with session_scope() as session:
            task = await session.get(AutonomousTask, task_id)
            if task:
                task.consecutive_failures = 0

        if result.inputs:
            await run_agent_background(thread_id, result.inputs)
    finally:
        await DevicePool.release_device(device_id, task_id=f"task-{task_id}")


@shared_task(name="engine_audit_structured_extraction")
async def engine_audit_structured_extraction(
    thread_id: str,
    project_id: int,
    user_id: str | None,
    run_id: str | None,
    summary: str,
    messages_dicts: list[dict],
    collected_schemas: list[dict],
):
    """
    Background Celery task that performs the heavy reasoning extraction (kimi-k2-thinking-turbo).
    """
    from app.core.engine.extraction.schema import build_dynamic_schema
    from app.core.events.schemas.lifecycle import ExtractionRequest, ExtractionCompletedEvent
    from app.core.events.base import system_bus
    from app.core.llm import InternalLLMService
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    if not collected_schemas:
        logger.info(f"[Celery] No extraction schemas requested for thread {thread_id}, skipping extraction.")
        return

    requests = [ExtractionRequest(**s) for s in collected_schemas]
    DynamicVerdict = build_dynamic_schema(requests, include_base_fields=False)
    if not DynamicVerdict:
        return

    # Reconstruct messages
    messages = []
    for m in messages_dicts:
        if m.get("type") == "human":
            messages.append(HumanMessage(**m))
        elif m.get("type") == "ai":
            messages.append(AIMessage(**m))
        elif m.get("type") == "system":
            messages.append(SystemMessage(**m))

    model_name = SystemConfigService.get_value("LLM_MODEL")

    extract_prompt = (
        f"You are extracting structured information from a completed session.\n\n"
        f"Session Summary:\n{summary}\n\n"
        f"Please extract information according to the requested schemas."
    )

    try:
        import asyncio
        response = await asyncio.wait_for(
            InternalLLMService.invoke_structured(
                messages=messages + [{"role": "system", "content": extract_prompt}],
                output_schema=DynamicVerdict,
                purpose="audit_extraction",
                temperature=0.1,
                max_tokens=4000,
                model_name=model_name,
                structured_output_method="json_mode",
            ),
            timeout=300.0,
        )
        if response:
            extracted_data = response.model_dump()
            extracted_data.pop("summary", None)
            extracted_data.pop("is_completed", None)

            event = ExtractionCompletedEvent(
                thread_id=thread_id,
                project_id=project_id,
                user_id=user_id,
                run_id=run_id,
                extracted_data=extracted_data,
            )
            logger.info(f"[Celery] 🚀 Publishing ExtractionCompletedEvent for thread {thread_id}")
            await system_bus.publish(event)
    except Exception as e:
        logger.error(f"[Celery] engine_audit_structured_extraction failed for thread {thread_id}: {e!r}")


@shared_task(name="engine_run_agent_background")
async def run_agent_background_task(thread_id: str, inputs: dict):
    """
    Execute an agent run in the background (within Celery/Huey worker).
    """
    from app.core.engine.background_agent import run_agent_background
    await run_agent_background(thread_id, inputs)


@shared_task(name="engine_resume_graph_background")
async def resume_graph_background_task(
    thread_id: str,
    inputs: dict,
    config: dict,
    run_label: str = "Resuming...",
    clear_human_request_flag: bool = False,
):
    """
    Execute graph resumption in the background (within Celery/Huey worker).
    """
    from app.core.engine.graph_runner import resume_graph_background
    await resume_graph_background(
        thread_id=thread_id,
        inputs=inputs,
        config=config,
        run_label=run_label,
        clear_human_request_flag=clear_human_request_flag,
    )
