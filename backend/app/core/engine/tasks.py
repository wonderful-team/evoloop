import logging
import os
import re
import shutil
import time

from sqlalchemy import func, select, text

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.learning.trace_recorder import sync_thread_to_graph
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.queue.factory import shared_task
from app.models import FileOperation

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


@shared_task(name="engine_persist_file_operation")
async def persist_file_operation_task(
    thread_id: str,
    message_id: str,
    file_path: str,
    operation: str,
    diff_content: str,
    original_content: str | None = None,
    run_id: str | None = None,
):
    """Background task to persist file movement/edit diffs to the database."""
    async with session_scope() as session:
        op = FileOperation(
            thread_id=thread_id,
            message_id=message_id,
            run_id=run_id,
            file_path=file_path,
            operation=operation,
            diff_content=diff_content,
            original_content=original_content,
        )
        session.add(op)
    logger.debug(f"[Celery] Persisted file operation for {file_path}")

    # Notify frontend via SSE
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

            thread_id = f"auton-{task_id}-{int(time.time())}"

            from app.utils import render_template
            prompt = render_template(
                "core/engine/tasks/autonomous_task.prompt.j2",
                intent_description=task.intent_description,
                skill_name=skill.name,
                skill_id=skill.id,
                device_id=device_id
            )

            # 2. Trigger Unified Dispatcher
            from app.core.engine.dispatch import dispatch_agent_run
            result = await dispatch_agent_run(
                thread_id=thread_id,
                message_content=prompt,
                project_id=project_id or DEFAULT_PROJECT_ID,
                goal_prefix="[Autonomous Task] ",
                metadata={
                    "autonomous_task_id": task_id,
                    "source_skill_id": skill.id,
                    "device_id": device_id  
                }
            )

            if result.status == "failed":
                raise RuntimeError(f"Dispatch failed for task {task_id}: {result.error}")

            logger.info(f"[Celery] Starting autonomous agent for task {task_id} on {device_id}")
            task.consecutive_failures = 0
            if result.inputs:
                await run_agent_background(thread_id, result.inputs)
    finally:
        await DevicePool.release_device(device_id, task_id=f"task-{task_id}")
