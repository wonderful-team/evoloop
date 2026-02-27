import asyncio
import logging
import os
import shutil
import time
from typing import Any

from celery import shared_task
from langchain_core.messages import SystemMessage
from sqlalchemy import text, select, desc

from app.core.config import settings
from app.core.learning.trace_recorder import sync_thread_to_graph
from app.core.memory import memory_manager
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

    asyncio.run(_run())


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

    asyncio.run(_run())


@shared_task(name="engine_snapshot_steps")
def snapshot_steps_task(
    thread_id: str,
    project_id: int,
    run_id: str | None,
    steps: list
):
    """Background task to persist executed steps to the last AI message."""
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
                            "time": t.get("time"),
                            "details": t.get("details"),
                        }
                        for t in steps
                    ]
                    last_msg.steps_snapshot = serialized_steps
            logger.debug(f"[Celery] Snapshotted {len(steps)} steps for thread {thread_id}")
        except Exception as e:
            logger.error(f"[Celery] Failed to snapshot steps: {e}")

    asyncio.run(_run())


def _parse_android_bounds(bounds_str: str) -> tuple[int, int, int, int] | None:
    """Parse bounds string like '[100,200][300,400]' to (x1, y1, x2, y2)."""
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
    if match:
        return tuple(map(int, match.groups()))
    return None


def _dehydrate_android_layout(xml_content: str) -> tuple[list[dict], str]:
    """Extract key UI elements and generate a concise summary from raw Android XML."""
    if not xml_content or not xml_content.strip():
        return [], "Empty layout."

    # Clean up XML: handle typical ADB dump noise
    xml_start = xml_content.find("<?xml")
    if xml_start == -1:
        xml_start = xml_content.find("<hierarchy")
    if xml_start >= 0:
        xml_end = xml_content.rfind(">")
        if xml_end > xml_start:
            xml_content = xml_content[xml_start: xml_end + 1]

    try:
        root = ET.fromstring(xml_content.strip())
    except Exception as e:
        return [], f"XML Parse Error: {str(e)}"

    elements = []
    summary_parts = []
    package_name = ""
    unique_labels = set()

    for node in root.iter():
        text = node.get("text", "") or node.get("content-desc", "")
        res_id = node.get("resource-id", "")
        clickable = node.get("clickable") == "true"
        focusable = node.get("focusable") == "true"
        pkg = node.get("package", "")
        if pkg:
            package_name = pkg

        # Dehydration rule: only keep interactive or labeled elements
        if not (text or res_id or clickable or (focusable and node.get("class", "").endswith("WebView"))):
            continue

        bounds_str = node.get("bounds", "")
        bounds = _parse_android_bounds(bounds_str)
        if not bounds:
            continue

        x1, y1, x2, y2 = bounds
        role = node.get("class", "").split('.')[-1]
        
        element = {
            "role": role,
            "label": text,
            "resource_id": res_id,
            "bounds": {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1},
            "clickable": clickable
        }
        elements.append(element)

        if text and text not in unique_labels and len(summary_parts) < 5:
            summary_parts.append(f"'{text}'")
            unique_labels.add(text)

    summary = f"Android Layout for {package_name}. Total {len(elements)} key elements."
    if summary_parts:
        summary += f" Contains: {', '.join(summary_parts)}."

    return elements, summary


@shared_task(name="engine_harvest_concepts")
def harvest_concepts_task(concepts_data: list[dict], project_id: int):
    """
    Background task to store harvested concepts in Neo4j with structural layout optimization.
    concepts_data: List of dicts with 'name' and 'description'.
    """
    if not concepts_data:
        return

    async def _run():
        logger.info(f"[Celery] Harvesting {len(concepts_data)} concepts...")
        for c in concepts_data:
            name = c["name"]
            description = c["description"]
            
            try:
                # Optimized logic for Android layouts
                if name.startswith("android_layout:"):
                    logger.info(f"Optimizing layout concept: {name}")
                    elements, summary = _dehydrate_android_layout(description)
                    
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
                await memory_manager.long_term.store_concept(mem_concept)
                logger.info(f"Harvested concept: {name}")
            except Exception as e:
                logger.warning(f"Failed to store concept {name}: {e}")

    asyncio.run(_run())


@shared_task(name="engine_record_episode")
def record_episode_task(
    thread_id: str,
    project_id: int,
    goal: str | None = None,
    result_summary: str | None = None,
    concept_names: list[str] | None = None,
    source_message_id: str | None = None,
):
    """
    Background task to sync thread trace to Neo4j Episode graph.
    """
    logger.info(f"[Celery] Recording episode for thread {thread_id} (Source: {source_message_id})...")

    async def _run():
        try:
            await sync_thread_to_graph(
                thread_id=thread_id,
                project_id=project_id,
                goal=goal,
                result_summary=result_summary,
                concept_names=concept_names,
                source_message_id=source_message_id,
            )
            logger.info(f"[Celery] Episode recorded for thread {thread_id}")
        except Exception as e:
            logger.error(f"[Celery] Failed to record episode: {e}")

    asyncio.run(_run())


@shared_task(name="engine_prune_checkpoints")
def prune_checkpoints_task(keep_days: int = 7):
    """
    Background task to prune old LangGraph checkpoints (Postgres).
    Prevents database bloat in conversation heavy environments.
    """
    async def _run():
        try:
            async with session_scope() as session:
                # Prune old checkpoints
                # Note: LangGraph Postgres schema uses 'checkpoints', 'checkpoint_writes', 'checkpoint_blobs'
                # We keep the most recent entries and prune based on timestamp.
                
                # 1. Prune checkpoint_writes (Execution history)
                q1 = text("DELETE FROM checkpoint_writes WHERE timestamp < now() - interval ':days day'")
                await session.execute(q1, {"days": keep_days})
                
                # 2. Prune checkpoints (State snapshots)
                # We only delete checkpoints that no longer have associated writes or are very old
                q2 = text("DELETE FROM checkpoints WHERE thread_id NOT IN (SELECT thread_id FROM checkpoint_writes)")
                await session.execute(q2)
                
                # 3. Prune blobs (Large data)
                q3 = text("DELETE FROM checkpoint_blobs WHERE thread_id NOT IN (SELECT thread_id FROM checkpoints)")
                await session.execute(q3)
                
                await session.commit()
            logger.info(f"[Celery] Pruned LangGraph checkpoints older than {keep_days} days.")
        except Exception as e:
            logger.error(f"[Celery] Failed to prune checkpoints: {e}")

    asyncio.run(_run())


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
):
    """Background task to persist agent messages to the database."""
    async def _run():
        from app.models import Message, MessageReference
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
            logger.error(f"[Celery] Failed to persist message: {e}")

    asyncio.run(_run())


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
        from app.domain.tools.git import HARVEST_PROMPT, ExtractionResult
        from app.infrastructure.llm.factory import LLMFactory
        from app.infrastructure.config.service import SystemConfigService
        import subprocess

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
            llm = LLMFactory.create_llm(temperature=0.0)
            structured_llm = llm.with_structured_output(ExtractionResult)
            user_lang = SystemConfigService.get_language_preference()
            lang_directive = f"\n\nLANGUAGE PROTOCOL:\nUser Language: {user_lang}\nDescription MUST be in {user_lang}."

            result = await structured_llm.ainvoke([
                SystemMessage(content=HARVEST_PROMPT.format(diff=diff_text) + lang_directive)
            ])

            if result and result.concepts:
                for concept in result.concepts:
                    mem_concept = MemConcept(concept.name, concept.description, project_id, concept.related_files)
                    await memory_manager.long_term.store_concept(mem_concept)
                    logger.info(f"[Celery] Harvested concept: {concept.name}")
        except Exception as e:
            logger.error(f"[Celery] Harvest extraction failed: {e}")

    asyncio.run(_run())
