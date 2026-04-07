import asyncio
import logging
import os
import shutil
import time
from typing import Any, cast

from langchain_core.messages import SystemMessage



# Unified task queue (Huey in embedded mode, Celery in full mode)
from app.infrastructure.queue.factory import shared_task
from sqlalchemy import text, select, desc, func

from app.core.config import settings
from app.constants import DEFAULT_PROJECT_ID
from app.core.learning.trace_recorder import sync_thread_to_graph

from app.core.memory.interfaces.long_term import Concept as MemConcept
from app.core.environment.events import UiTreeObservedEvent, event_bus
from app.infrastructure.database.sql.database import session_scope
from app.models import FileOperation
import xml.etree.ElementTree as ET
import re

logger = logging.getLogger(__name__)


@shared_task(name="engine_persist_file_operation")
def persist_file_operation_task(
    thread_id: str,
    message_id: str,
    file_path: str,
    operation: str,
    diff_content: str,
    original_content: str | None = None
):
    """Background task to persist file movement/edit diffs to the database."""
    async def _run():
        try:
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
        except Exception as e:
            logger.error(f"[Celery] Failed to persist file operation: {e}")

    async def _run_with_flush():
        try:
            await _run()
        finally:
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
            
    asyncio.run(_run_with_flush())


@shared_task(name="engine_upload_cloud_log")
def upload_cloud_log_task(
    device_id: int,
    thread_id: str,
    log_type: str,
    content: Any,
    name: str | None = None,
    command_id: int | None = None,
    project_id: int | None = None
):
    """Background task to upload logs to EvoCloud for persistence."""
    async def _run():
        try:
            from app.core.evocloud import evocloud_manager
            if not evocloud_manager._initialized:
                evocloud_manager.initialize()
            
            await evocloud_manager.api.upload_log(
                device_id, thread_id, log_type, content, 
                name=name, command_id=command_id, project_id=project_id
            )
            logger.debug(f"[Celery] Uploaded cloud log: {log_type}")
        except Exception as e:
            logger.error(f"[Celery] Cloud log upload failed: {e}")

    async def _run_with_flush():
        try:
            await _run()
        finally:
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
            
    asyncio.run(_run_with_flush())


@shared_task(name="engine_snapshot_steps")
def snapshot_steps_task(
    thread_id: str,
    project_id: int,
    run_id: str | None,
    steps: list
):
    """Background task to persist executed steps to the last AI message.
    
    Note: This now APPENDS to existing steps rather than overwriting,
    supporting the "Real-time Attribution" (方案 A) design where steps
    are incrementally attributed to the AI message active when they ran.
    """
    async def _run():
        try:
            from app.models import Message
            async with session_scope() as session:
                stmt = (
                    select(Message)
                    .where(Message.thread_id == thread_id)
                    .where(Message.role == "ai")
                )
                if run_id:
                    stmt = stmt.where(Message.run_id == run_id)
                stmt = stmt.order_by(desc(Message.sequence_number)).limit(1)

                result = await session.execute(stmt)
                last_msg = result.scalar_one_or_none()

                if last_msg:
                    serialized_steps = [
                        {
                            "id": t.get("id"),
                            "name": t.get("name"),
                            "status": t.get("status"),
                            "type": t.get("type"),
                            "parent_id": t.get("parent_id"),
                            "time": t.get("time"),
                            "details": t.get("details"),
                        }
                        for t in steps
                    ]
                    
                    # Append to existing steps instead of overwriting
                    existing_steps = last_msg.steps_snapshot or []
                    last_msg.steps_snapshot = existing_steps + serialized_steps
                    
            logger.debug(f"[Celery] Snapshotted {len(steps)} steps for thread {thread_id}")
        except Exception as e:
            logger.error(f"[Celery] Failed to snapshot steps: {e}")

    async def _run_with_flush():
        try:
            await _run()
        finally:
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
            
    asyncio.run(_run_with_flush())


@shared_task(name="engine_harvest_concepts")
def harvest_concepts_task(concepts_data: list[dict], project_id: int):
    """
    Background task to store harvested concepts in Neo4j with structural layout optimization.
    concepts_data: List of dicts with 'name' and 'description'.
    """
    if not concepts_data:
        return

    async def _run():
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
                        
                        await event_bus.publish(UiTreeObservedEvent(
                            platform="android",
                            bundle_id=bundle_id,
                            window_title=name.replace("android_layout:", "").split('(')[0].strip(),
                            elements=elements
                        ))
                        
                        # 2. Use dehydrated summary as Concept description
                        description = summary
                        logger.debug(f"Dehydrated {name} into summary: {summary}")

                mem_concept = MemConcept(name, description, project_id, [])
                # Use singleton container to store concept
                from app.core.memory.lifespan import MemoryLifespanManager
                if not MemoryLifespanManager.is_initialized():
                    await MemoryLifespanManager.ainitialize()
                container = MemoryLifespanManager.get_container()
                await container.memory_manager.long_term.store_concept(mem_concept)
                logger.info(f"Harvested concept: {name}")
            except Exception as e:
                logger.warning(f"Failed to store concept {name}: {e}")

    async def _run_with_flush():
        try:
            await _run()
        finally:
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
            
    asyncio.run(_run_with_flush())


@shared_task(name="engine_record_episode")
def record_episode_task(
    thread_id: str,
    project_id: int,
    goal: str | None = None,
    result_summary: str | None = None,
    concept_names: list[str] | None = None,
    source_message_id: str | None = None,
    auto_synthesize: bool = False,
):
    """
    Background task to sync thread trace to Neo4j Episode graph.
    If auto_synthesize is True, it also triggers the WorkflowSynthesizer.
    """
    logger.info(f"[Celery] Recording episode for thread {thread_id} (Source: {source_message_id}, AutoSynth: {auto_synthesize})...")

    async def _run():
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
                        logger.info(f"[Celery] ⏩ Skill synthesis skipped (no unique pattern found)")
                else:
                    logger.info(f"[Celery] ⏩ Skill synthesis skipped (insufficient events: {event_count})")

        except Exception as e:
            logger.error(f"[Celery] Failed to record episode/synthesize: {e}", exc_info=True)

    async def _run_with_flush():
        try:
            await _run()
        finally:
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
            
    asyncio.run(_run_with_flush())


@shared_task(name="engine_prune_checkpoints")
def prune_checkpoints_task(keep_days: int = 7):
    """
    Background task to prune old LangGraph checkpoints (Postgres).
    Prevents database bloat in conversation heavy environments.
    """
    async def _run():
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

    async def _run_with_flush():
        try:
            await _run()
        finally:
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
            
    asyncio.run(_run_with_flush())


@shared_task(name="engine_persist_message")
def persist_message_task(
    thread_id: str,
    project_id: int,
    role: str,
    content: str,
    thinking: str | None = None,
    sequence_number: int = 0,
    run_id: str | None = None,
    status: str = "completed",
    parent_id: str | None = None,
    tool_calls: list | None = None,
    references: list[dict] | None = None,
    action_type: str = "text",
    category: str | None = None,
):
    """Background task to persist agent messages to the database.
    
    Note: is_visible is now completely determined by category.
    No manual calculation based on role/content.
    """
    async def _run():
        from app.models import Message, MessageReference
        from app.core.messaging.category import MessageCategory
        from uuid import UUID
        
        try:
            async with session_scope() as session:
                target_parent_id = parent_id
                if not target_parent_id:
                    # Find last message in thread
                    stmt = (
                        select(Message.id)
                        .where(Message.thread_id == thread_id)
                        .order_by(desc(Message.sequence_number))
                        .limit(1)
                    )
                    res = await session.execute(stmt)
                    target_parent_id = res.scalar_one_or_none()

                # is_visible is completely determined by category
                # This ensures consistency across the entire system
                is_visible = True
                if category:
                    try:
                        cat_enum = MessageCategory(category)
                        is_visible = cat_enum in MessageCategory.get_visible_categories()
                    except ValueError:
                        # Unknown category, default to visible
                        is_visible = True

                log = Message(
                    thread_id=thread_id,
                    project_id=project_id,
                    role=role,
                    content=content,
                    thinking=thinking,
                    sequence_number=sequence_number,
                    run_id=run_id,
                    status=status,
                    parent_id=target_parent_id,
                    tool_calls=tool_calls,
                    action_type=action_type,
                    is_visible=is_visible,
                    category=category,
                )
                session.add(log)
                await session.flush()  # Get ID for references

                if references:
                    for ref in references:
                        mr = MessageReference(
                            id=str(UUID(int=hash(f"{log.id}-{ref['target_id']}-{time.time()}") & ((1 << 128) - 1))),
                            message_id=log.id,
                            type=ref["type"],
                            target_id=ref["target_id"],
                            target_name=ref["target_name"],
                        )
                        session.add(mr)

            logger.debug(f"[Celery] Persisted message {sequence_number} with {len(references or [])} refs for thread {thread_id}")
        except Exception as e:
            error_msg = f"[Celery] Failed to persist message: {type(e).__name__}: {e}"
            logger.error(error_msg)
            # Print as fallback to ensure error is visible even if logger level is high
            print(f"ERROR: {error_msg}", flush=True)
            import traceback
            traceback.print_exc()

    async def _run_with_flush():
        try:
            await _run()
        finally:
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
            
    asyncio.run(_run_with_flush())


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
def git_harvest_task(cwd: str, project_id: int):
    """
    Background task to extract knowledge concepts from git diff.
    """
    async def _run():
        import subprocess
        from app.models.schemas.git import ExtractionResult
        from app.infrastructure.config.service import SystemConfigService

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
                "tool/git_harvest.prompt.j2",
                diff_content=diff_text,
                user_language=user_lang
            )

            # Use InternalLLMService for structured extraction
            from app.core.llm import InternalLLMService
            result = await InternalLLMService.invoke_structured(
                messages=[
                    {"role": "system", "content": prompt_text}
                ],
                purpose="memory_extraction",
                output_schema=ExtractionResult,
                temperature=0.0,
            )

            if isinstance(result, ExtractionResult) and result.concepts:
                # Use singleton container to store concepts
                from app.core.memory.lifespan import MemoryLifespanManager
                if not MemoryLifespanManager.is_initialized():
                    await MemoryLifespanManager.ainitialize()
                container = MemoryLifespanManager.get_container()
                for concept in result.concepts:
                    mem_concept = MemConcept(concept.name, concept.description, project_id, concept.related_files)
                    await container.memory_manager.long_term.store_concept(mem_concept)
                    logger.info(f"[Celery] Harvested concept: {concept.name}")
        except Exception as e:
            logger.error(f"[Celery] Harvest extraction failed: {e}")

    async def _run_with_flush():
        try:
            await _run()
        finally:
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
            
    asyncio.run(_run_with_flush())


@shared_task(name="engine_reconcile_skill_macro")
def reconcile_skill_macro_task(skill_id: int, thread_id: str):
    """
    Background task to reconcile a broken skill macro with a successful agentic recovery trace.
    This effectively "heals" the macro in the database for future deterministic runs.
    """
    async def _run():
        from app.core.learning.skill_synthesizer import WorkflowSynthesizer
        from app.models.learning import LearnedSkill
        import json

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

    async def _run_with_flush():
        try:
            await _run()
        finally:
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
            
    asyncio.run(_run_with_flush())


@shared_task(name="engine_scheduler_tick")
def engine_scheduler_tick():
    """
    Background task to poll for due autonomous tasks.
    Triggered by Celery Beat.
    """
    async def _run():
        try:
            from app.infrastructure.scheduler.service import SchedulerService
            await SchedulerService.tick()
        except Exception as e:
            logger.error(f"[Celery] Scheduler tick failed: {e}")

    async def _run_with_flush():
        try:
            await _run()
        finally:
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
            
    asyncio.run(_run_with_flush())


@shared_task(name="run_autonomous_task_execution")
def run_autonomous_task_execution(task_id: int, project_id: int | None = None):
    """
    Background task to execute an autonomous task.
    Constructs an agent session from the task's intent and skill.
    Now supports multi-device reservation.
    """
    async def _run():
        from app.models.scheduler import AutonomousTask
        from app.models.learning import LearnedSkill
        from app.core.engine.background_agent import run_agent_background
        from app.core.environment.devices import DevicePool
        
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
                    "autonomous/autonomous_task.prompt.j2",
                    intent_description=task.intent_description,
                    skill_name=skill.name,
                    skill_id=skill.id,
                    device_id=device_id
                )
                
                inputs = {
                    "messages": [{"type": "human", "content": prompt}],
                    "project_id": project_id or DEFAULT_PROJECT_ID,
                    "task_title": f"Autonomous: {task.intent_description[:30]}...",
                    "metadata": {
                        "autonomous_task_id": task_id,
                        "source_skill_id": skill.id,
                        "device_id": device_id  # Inject device_id for tools to pick up
                    }
                }
                
                logger.info(f"[Celery] Starting autonomous agent for task {task_id} on {device_id} (Thread: {thread_id})")
                
                # Update task status: successful start
                task.consecutive_failures = 0 
                
                await run_agent_background(thread_id, inputs)
                
        except Exception as e:
            logger.error(f"[Celery] Autonomous task execution failed for {task_id}: {e}")
        finally:
            if device_id:
                await DevicePool.release_device(device_id, task_id=f"task-{task_id}")

    async def _run_with_flush():
        try:
            await _run()
        finally:
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
            
    asyncio.run(_run_with_flush())
