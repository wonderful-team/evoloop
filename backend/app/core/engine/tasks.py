import logging
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
    import time

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
        metadata={
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
    original_content: str | None = None
):
    """Background task to persist file movement/edit diffs to the database."""
    async with session_scope() as session:
        op = FileOperation(
            thread_id=thread_id,
            message_id=message_id,
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
    In full mode this goes to Neo4j; in embedded mode it goes to the file backend.
    concepts_data: List of dicts with 'name' and 'description'.
    """
    if not concepts_data:
        return

    from app.core.environment.android import android_service
    logger.info(f"[Celery] Harvesting {len(concepts_data)} concepts...")
    for c in concepts_data:
        name = c["name"]
        description = c["description"]

        try:
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
                        elements=elements,
                    )

                    # 2. Use dehydrated summary as Concept description
                    description = summary
                    logger.debug(f"Dehydrated {name} into summary: {summary}")

            # Use unified MemoryManager interface
            from app.core.memory.lifespan import MemoryLifespanManager
            import asyncio
            # Module-level lock to prevent TOCTOU between is_initialized() and ainitialize()
            _memory_init_lock = asyncio.Lock()
            async with _memory_init_lock:
                if not MemoryLifespanManager.is_initialized():
                    await MemoryLifespanManager.ainitialize()
            container = MemoryLifespanManager.get_container()
            await container.memory_manager.store_concept(
                name=name,
                description=description,
                project_id=project_id,
            )
            logger.info(f"Harvested concept: {name}")
        except Exception as e:
            logger.warning(f"Failed to store concept {name}: {e}")


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
    If auto_synthesize is True, it also triggers the WorkflowSynthesizer.
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

            if event_count and event_count >= 3: # Minimum threshold for a synthesis-worthy skill
                logger.info(f"[Celery] 🧬 Auto-triggering skill synthesis for thread {thread_id} ({event_count} events)")
                synthesizer = WorkflowSynthesizer(thread_id=thread_id)
                result = await synthesizer.synthesize()
                if result:
                    logger.info(f"[Celery] ✅ Skill synthesis complete: {result.name}")
                else:
                    logger.info("[Celery] ⏩ Skill synthesis skipped (no unique pattern found)")
            else:
                logger.info(f"[Celery] ⏩ Skill synthesis skipped (insufficient events: {event_count})")

    finally:
        ContextManager.reset(token)


@shared_task(name="engine_prune_checkpoints")
async def prune_checkpoints_task(keep_days: int = 7):
    """
    Background task to prune old LangGraph checkpoints (Postgres).
    Prevents database bloat in conversation heavy environments.
    """
    try:
        is_sqlite = settings.EMBEDDED_MODE or "sqlite" in settings.SQLALCHEMY_DATABASE_URI

        async with session_scope() as session:
            if is_sqlite:
                # 1. Prune 'writes' table (LangGraph SQLite uses 'writes' instead of 'checkpoint_writes')
                # Since SQLite schema lacks a timestamp, we prune writes which are most volatile.
                # We keep writes for very recent checkpoints to avoid breaking active runs.
                await session.execute(text("DELETE FROM writes WHERE thread_id NOT IN (SELECT thread_id FROM checkpoints)"))
                logger.info("[Celery] Pruned orphaned LangGraph 'writes' in SQLite.")
            else:
                # Postgres pruning (Original logic)
                # 1. Prune checkpoint_writes (Execution history)
                q1 = text("DELETE FROM checkpoint_writes WHERE timestamp < now() - interval ':days day'")
                await session.execute(q1, {"days": keep_days})

                # 2. Prune checkpoints (State snapshots)
                q2 = text("DELETE FROM checkpoints WHERE thread_id NOT IN (SELECT thread_id FROM checkpoint_writes)")
                await session.execute(q2)

                # 3. Prune blobs (Large data)
                q3 = text("DELETE FROM checkpoint_blobs WHERE thread_id NOT IN (SELECT thread_id FROM checkpoints)")
                await session.execute(q3)

            await session.commit()
        logger.info(f"[Celery] Pruned LangGraph checkpoints/writes (Keep: {keep_days} days).")
    except Exception as e:
        logger.error(f"[Celery] Failed to prune checkpoints: {e}")

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
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            try:
                if os.path.getmtime(file_path) < cutoff:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
            except Exception as e:
                logger.warning(f"Failed to delete artifact {file_path}: {e}")


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

    # 1. Get Diff
    try:
        cmd = ["git", "diff", "HEAD"]
        process = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=15)
        diff_text = process.stdout
        if not diff_text.strip():
            return
        if len(diff_text) > 10000:
            diff_text = diff_text[:10000] + "\n...(truncated)"
    except Exception as e:
        logger.error(f"[Celery] Git diff failed: {e}")
        return

    # 2. Extract
    try:
        user_lang = SystemConfigService.get_language_preference()

        from app.utils import render_template
        prompt_text = render_template(
            "core/engine/tasks/git_harvest.prompt.j2",
            diff_content=diff_text,
            user_language=user_lang
        )

        # Use InternalLLMService for structured extraction
        from app.core.llm import InternalLLMService
        from app.infrastructure.config.service import SystemConfigService
        model_name = SystemConfigService.get_value("LLM_MODEL")
        result = await InternalLLMService.invoke_structured(
            messages=[
                {"role": "system", "content": prompt_text}
            ],
            purpose="memory_extraction",
            output_schema=GitConceptExtractionResult,
            temperature=0.0,
            model_name=model_name,
        )

        if isinstance(result, GitConceptExtractionResult) and result.concepts:
            # Use singleton container to store concepts
            from app.core.memory.lifespan import MemoryLifespanManager
            import asyncio
            # Module-level lock to prevent TOCTOU between is_initialized() and ainitialize()
            _memory_init_lock = asyncio.Lock()
            async with _memory_init_lock:
                if not MemoryLifespanManager.is_initialized():
                    await MemoryLifespanManager.ainitialize()
            container = MemoryLifespanManager.get_container()
            from app.core.memory.schemas import Concept as MemConcept
            for concept in result.concepts:
                mem_concept = MemConcept(
                    name=concept.name,
                    description=concept.description,
                    project_id=project_id,
                    related_files=concept.related_files
                )
                await container.memory_manager.store_concept(mem_concept)
                logger.info(f"[Celery] Harvested concept: {concept.name}")
    except Exception as e:
        logger.error(f"[Celery] Harvest extraction failed: {e}")
    finally:
        ContextManager.reset(token)


@shared_task(name="engine_reconcile_skill_macro")
async def reconcile_skill_macro_task(skill_id: int, thread_id: str, model: str | None = None):
    """
    Background task to reconcile a broken skill macro with a successful agentic recovery trace.
    This effectively "heals" the macro in the database for future deterministic runs.
    """
    from app.core.learning.skill_synthesizer import WorkflowSynthesizer
    from app.models.learning import LearnedSkill

    # Initialize background context
    ctx = EvoContext(thread_id=thread_id, active_model=model)
    token = ContextManager.set(ctx)

    try:
        logger.info(f"[Celery] Reconciling Skill {skill_id} from thread {thread_id}...")

        # 1. Synthesize the correction from the successful thread
        synthesizer = WorkflowSynthesizer(thread_id)
        repaired_skill = await synthesizer.synthesize()

        if not repaired_skill.macro_script:
            logger.warning(f"[Celery] No valid macro synthesized from recovery thread {thread_id}. Aborting patch.")
            return

        # 2. Patch the original skill in the database
        async with session_scope() as session:
            stmt = select(LearnedSkill).where(LearnedSkill.id == skill_id)
            result = await session.execute(stmt)
            original_skill = result.scalar_one_or_none()

            if original_skill:
                # Update macro and instructions (心法)
                original_skill.macro_script = repaired_skill.macro_script
                if repaired_skill.instructions:
                    original_skill.instructions = repaired_skill.instructions

                logger.info(f"[Celery] ✅ Skill {skill_id} ('{original_skill.name}') has been self-healed and updated in DB.")
            else:
                logger.error(f"[Celery] Target Skill {skill_id} not found for reconciliation.")

    except Exception as e:
        logger.error(f"[Celery] Macro reconciliation failed: {e}")
    finally:
        ContextManager.reset(token)


@shared_task(name="engine_scheduler_tick")
async def engine_scheduler_tick():
    """
    Background task to poll for due autonomous tasks.
    Triggered by Celery Beat.
    """
    try:
        from app.infrastructure.scheduler.service import SchedulerService
        await SchedulerService.tick()
    except Exception as e:
        logger.error(f"[Celery] Scheduler tick failed: {e}")


@shared_task(name="run_autonomous_task_execution")
async def run_autonomous_task_execution(task_id: int, project_id: int | None = None):
    """
    Background task to execute an autonomous task.
    Constructs an agent session from the task's intent and skill.
    Now supports multi-device reservation.
    """
    from app.core.engine.background_agent import run_agent_background
    from app.core.environment.devices import DevicePool
    from app.models.learning import LearnedSkill
    from app.models.scheduler import AutonomousTask

    device_id = None
    try:
        # 1. Reserve a device
        device_id = await DevicePool.reserve_device(task_id=f"task-{task_id}")
        if not device_id:
            logger.warning(f"[Celery] No devices available for task {task_id}. Re-queuing...")
            # Optional: retry with delay or just fail
            raise ValueError("No available Android devices.")

        async with session_scope() as session:
            task = await session.get(AutonomousTask, task_id)
            if not task:
                logger.error(f"[Celery] Autonomous task {task_id} not found.")
                return

            skill = await session.get(LearnedSkill, task.skill_id)
            if not skill:
                logger.error(f"[Celery] Skill {task.skill_id} for task {task_id} not found.")
                return

            # Construct execution context
            thread_id = f"auton-{task_id}-{int(time.time())}"

            # Instruction to the Agent (rendered from template)
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
                    "device_id": device_id  # Inject device_id for tools to pick up
                }
            )

            if result.status == "failed":
                logger.error(f"[Celery] Dispatch failed for task {task_id}: {result.error}")
                return

            logger.info(f"[Celery] Starting autonomous agent for task {task_id} on {device_id} (Thread: {thread_id})")

            # Update task status: successful start
            task.consecutive_failures = 0

            await run_agent_background(thread_id, result.inputs)

    except Exception as e:
        logger.error(f"[Celery] Autonomous task execution failed for {task_id}: {e}")
    finally:
        if device_id:
            await DevicePool.release_device(device_id, task_id=f"task-{task_id}")
