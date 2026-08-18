import asyncio
import logging
import os
import re
import shutil
import time

from sqlalchemy import desc, func, select

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.execution.macro import (
    MacroScriptCompiler,
    create_macro_from_synthesis,
)
from app.core.learning.trace.recorder import sync_thread_to_graph
from app.infrastructure.database import session_scope
from app.infrastructure.queue.factory import periodic_task, shared_task
from app.models import FileOperation, Message
from app.utils.parameters import normalize_parameters
from app.utils.pydantic_helpers import clean_none_values

logger = logging.getLogger(__name__)


async def _notify_file_operation(
    thread_id: str, message_id: str, file_path: str, operation: str
):
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
    # SSE-only: Celery-side file operation progress is not a persisted chat
    # message and should never be pushed to mobile/voice channels.
    await publisher.publish(block, channels={"sse"})
    logger.debug(f"[Task] Published file operation event for {file_path}")


async def _persist_file_operation(
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
            stmt_msg = (
                select(Message.id)
                .where(
                    Message.thread_id == thread_id, Message.tool_call_id == tool_call_id
                )
                .order_by(desc(Message.sequence_number))
            )
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
        logger.info(f"[Task] Persisted file operation for {file_path}")

    # --- [Phase 2] 同步到消息标准化引用并触发实时更新 ---
    from app.core.engine.message.repository import MessageRepository

    repo = MessageRepository(thread_id=thread_id)
    await repo.sync_changeset_reference(
        message_id=message_id,
        file_path=file_path,
        operation=operation,
        run_id=run_id,
        tool_call_id=tool_call_id,
        diff_content=diff_content,
    )


@shared_task(name="engine_persist_file_operation")  # type: ignore[reportCallIssue]
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
    from sqlalchemy.orm import selectinload

    from app.core.engine.message.mapper import BlockMapper
    from app.core.engine.message.publisher import MessagePublisher

    await _persist_file_operation(
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
        stmt = (
            select(Message)
            .where(Message.id == message_id)
            .options(selectinload(Message.references))
        )
        result = await session.execute(stmt)
        db_msg = result.scalar_one_or_none()

        if db_msg:
            block = BlockMapper.from_db(db_msg)
            publisher = MessagePublisher(thread_id=thread_id)
            # SSE-only: this is an incremental "update" refresh for the web
            # message that the user already sees; skip mobile/voice broadcast.
            # action="update" 会触发前端对应消息的局部刷新
            await publisher.publish(block, action="update", channels={"sse"})

    # 原有的细粒度通知逻辑保留
    await _notify_file_operation(thread_id, message_id, file_path, operation)

    # Notify sidebar changeset panel to refresh
    try:
        from app.core.events import system_bus
        from app.core.file.event import ChangesetUpdatedEvent

        await system_bus.publish(
            ChangesetUpdatedEvent(
                thread_id=thread_id,
                message_id=message_id,
                file_path=file_path,
                operation=operation,
            )
        )
    except Exception as e:
        logger.warning(f"[Task] Failed to publish changeset updated event: {e}", exc_info=True)


@shared_task(name="engine_harvest_concepts")  # type: ignore[reportCallIssue]
async def harvest_concepts_task(concepts_data: list[dict], project_id: int):
    """
    Background task to store harvested concepts into the memory system.
    """
    if not concepts_data:
        return

    from app.core.environment.android import android_service
    from app.core.memory.lifespan import MemoryLifespanManager

    logger.info(f"[Task] Harvesting {len(concepts_data)} concepts...")

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

                from app.core.environment.event.publishers import (
                    publish_ui_tree_observed,
                )

                await publish_ui_tree_observed(
                    platform="android",
                    bundle_id=bundle_id,
                    window_title=name.replace("android_layout:", "")
                    .split("(")[0]
                    .strip(),
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


@shared_task(name="engine_record_episode")  # type: ignore[reportCallIssue]
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
    logger.info(f"[Task] Recording episode for thread {thread_id} (Source: {source_message_id}, AutoSynth: {auto_synthesize})...")

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
        logger.info(f"[Task] Episode recorded for thread {thread_id}")

        if auto_synthesize:
            from app.core.learning.trace.parser import TraceParser
            from app.core.learning.workflow_synthesizer import WorkflowSynthesizer
            from app.models.learning import TraceEvent

            # Check if there are meaningful events to synthesize
            async with session_scope() as db:
                stmt = select(func.count(TraceEvent.id)).where(TraceEvent.thread_id == thread_id)
                count_res = await db.execute(stmt)
                event_count = count_res.scalar()

            if event_count and event_count >= 3:
                logger.info(f"[Task] 🧬 Auto-triggering skill synthesis for thread {thread_id} ({event_count} events)")
                parser = TraceParser(thread_id=thread_id)
                sequence = await parser.parse()
                synthesizer = WorkflowSynthesizer(thread_id=thread_id, sequence=sequence)
                result = await synthesizer.synthesize()
                if result and result.skill:
                    # Persist through the single creation service so the skill
                    # lands as pending_review (user confirmation required),
                    # exactly like the REST /skills/synthesize path.
                    from app.core.events.publishers import (
                        publish_macro_mutated,
                        publish_skill_mutated,
                    )
                    from app.core.learning.skills.lifecycle import create_from_synthesis

                    macro_script = MacroScriptCompiler().compile(sequence).to_yaml()

                    async with session_scope() as db:
                        db_skill = await create_from_synthesis(
                            db,
                            member_id=0,
                            name=result.skill.name,
                            description=result.skill.description,
                            trigger_patterns=result.skill.trigger_patterns,
                            parameters=result.skill.parameters,
                            preconditions=result.skill.preconditions,
                            tools_used=result.skill.tools_used,
                            source_thread_id=result.skill.source_thread_id,
                            source_session_id=result.skill.source_session_id,
                            instructions=result.skill.instructions,
                        )

                        db_macro = await create_macro_from_synthesis(
                            db,
                            name=db_skill.name,
                            description=db_skill.description,
                            trigger_patterns=db_skill.trigger_patterns,
                            parameters=normalize_parameters(result.skill.parameters),
                            macro_script=macro_script,
                            fallback_skill_id=db_skill.id,
                            source_thread_id=result.skill.source_thread_id,
                            project_id=project_id,
                        )
                        db_skill.macro_id = db_macro.id
                    await publish_skill_mutated(skill_id=db_skill.id, action="create")
                    await publish_macro_mutated(db_macro.id, action="create")
                    logger.info(f"[Task] ✅ Skill synthesis complete: {result.skill.name} (pending_review)")
                else:
                    logger.info("[Task] ⏩ Skill synthesis skipped (no unique pattern found)")
    finally:
        ContextManager.reset(token)


@shared_task(name="engine_cleanup_artifacts")  # type: ignore[reportCallIssue]
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

        logger.info(f"[Task] Cleaning up old artifacts in {directory}...")
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
                logger.warning(f"Failed to delete artifact {entry.path}: {e}", exc_info=True)


@shared_task(name="engine_git_harvest")  # type: ignore[reportCallIssue]
async def git_harvest_task(cwd: str, project_id: int, model: str | None = None):
    """
    Background task to extract knowledge concepts from git diff.
    """
    ctx = EvoContext(project_id=project_id, active_model=model)
    token = ContextManager.set(ctx)

    from app.infrastructure.config.service import SystemConfigService
    from app.models.schemas.git import GitConceptExtractionResult

    try:
        # 1. Get Diff
        if not os.path.exists(cwd):
            logger.warning(f"[Task] Skipping git harvest: Directory '{cwd}' does not exist.")
            return

        cmd = ["git", "diff", "HEAD"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await asyncio.wait_for(process.communicate(), timeout=15)
        diff_text = stdout_bytes.decode("utf-8", errors="replace")
        if not diff_text.strip():
            return

        if len(diff_text) > 10000:
            diff_text = diff_text[:10000] + "\n...(truncated)"

        # 2. Extract
        user_lang = SystemConfigService.get_language_preference()

        from app.utils.template import render_template

        prompt_text = render_template(
            "core/engine/tasks/git_harvest.prompt.j2",
            diff_content=diff_text,
            user_language=user_lang,
        )

        from app.infrastructure.llm import InternalLLMService

        result = await InternalLLMService.invoke_structured(
            messages=[{"role": "system", "content": prompt_text}],
            purpose="memory_extraction",
            output_schema=GitConceptExtractionResult,
            temperature=0.0,
            max_tokens=4000,
        )

        if result.concepts:
            from app.core.memory.lifespan import MemoryLifespanManager
            from app.core.memory.schemas import Concept

            if not MemoryLifespanManager.is_initialized():
                await MemoryLifespanManager.ainitialize()
            container = MemoryLifespanManager.get_container()

            for concept in result.concepts:
                mem_concept = Concept(
                    name=concept.name,
                    description=concept.description,
                    project_id=project_id,
                    related_files=concept.related_files,
                )
                await container.memory_manager.store_concept(mem_concept)
                logger.info(f"[Task] Harvested concept: {concept.name}")
    finally:
        ContextManager.reset(token)


@shared_task(name="engine_reconcile_skill_macro")  # type: ignore[reportCallIssue]
async def reconcile_skill_macro_task(skill_id: int, thread_id: str, model: str | None = None):
    """
    Background task to reconcile a broken skill macro.
    """
    from app.core.events.publishers import publish_skill_mutated
    from app.core.learning.trace.parser import TraceParser
    from app.core.learning.workflow_synthesizer import WorkflowSynthesizer
    from app.models.learning import TraceEvent

    # Pre-check: ensure there are enough trace events to synthesize from
    async with session_scope() as db:
        stmt = select(func.count(TraceEvent.id)).where(TraceEvent.thread_id == thread_id)
        count_res = await db.execute(stmt)
        event_count = count_res.scalar()

    if not event_count or event_count < 3:
        logger.warning(
            f"[Task] Skipping skill reconciliation for {thread_id}: "
            f"only {event_count or 0} trace events found (need >= 3)."
        )
        return

    ctx = EvoContext(thread_id=thread_id, active_model=model)
    token = ContextManager.set(ctx)

    try:
        logger.info(f"[Task] Reconciling Skill {skill_id} from thread {thread_id}...")
        parser = TraceParser(thread_id=thread_id)
        sequence = await parser.parse()
        synthesizer = WorkflowSynthesizer(thread_id=thread_id, sequence=sequence)
        repaired_skill = await synthesizer.synthesize()
        macro_script = MacroScriptCompiler().compile(sequence).to_yaml()

        if not macro_script:
            logger.warning(f"[Task] No valid macro synthesized from recovery thread {thread_id}. Aborting patch.")
            return

        healed = False
        healed_macro_ids: list[int] = []
        async with session_scope() as session:
            from app.core.learning.skills.lifecycle import patch_skill
            from app.core.learning.skills.repository import skill_repository

            original_skill = await skill_repository.get_by_id(skill_id, db=session)

            if original_skill:
                healed = True
                if repaired_skill.skill and repaired_skill.skill.instructions:
                    await patch_skill(
                        original_skill, instructions=repaired_skill.skill.instructions
                    )

                # Chain-heal paired flywheel macros (macros table is the
                # authoritative store for deterministic scripts).
                from app.core.execution.macro import (
                    create_macro_from_synthesis,
                    list_macros,
                    update_macro,
                )

                if original_skill.macro_id:
                    if await update_macro(
                        original_skill.macro_id, {"macro_script": macro_script}, db=session
                    ):
                        healed_macro_ids.append(original_skill.macro_id)
                else:
                    existing_rows = await list_macros(
                        fallback_skill_id=skill_id, db=session
                    )
                    existing = existing_rows[0] if existing_rows else None
                    if existing is not None:
                        await update_macro(
                            existing.id, {"macro_script": macro_script}, db=session
                        )
                        await patch_skill(original_skill, macro_id=existing.id)
                        healed_macro_ids.append(existing.id)
                    else:
                        new_macro = await create_macro_from_synthesis(
                            session,
                            name=original_skill.name,
                            description=original_skill.description or "",
                            trigger_patterns=original_skill.trigger_patterns or [],
                            parameters=original_skill.parameters or [],
                            macro_script=macro_script,
                            fallback_skill_id=original_skill.id,
                            source_thread_id=original_skill.source_thread_id,
                            project_id=original_skill.project_id,
                            member_id=original_skill.member_id,
                        )
                        await patch_skill(original_skill, macro_id=new_macro.id)
                        healed_macro_ids.append(new_macro.id)

        # Publish AFTER commit: subscribers re-query the row in a new session
        # (file export + route-index upsert) and must see the patched macro.
        if healed:
            logger.info(f"[Task] ✅ Skill {skill_id} has been self-healed.")
            await publish_skill_mutated(skill_id=skill_id, action="update")
            from app.core.events.publishers import publish_macro_mutated

            for macro_id in healed_macro_ids:
                await publish_macro_mutated(macro_id, action="update")
    finally:
        ContextManager.reset(token)


@periodic_task(cron="* * * * *", name="engine_scheduler_tick_periodic")
def engine_scheduler_tick_periodic():
    """每分钟轮询值守/自主任务的周期调度。

    复用 engine_scheduler_tick 的 tick 逻辑（Celery beat 的 60s 调度
    在 Huey 模式不生效，此处用 Huey periodic 替代）。
    """
    engine_scheduler_tick.delay()


@shared_task(name="engine_scheduler_tick")  # type: ignore[reportCallIssue]
async def engine_scheduler_tick():
    """
    Background task to poll for due autonomous tasks.
    """
    from app.infrastructure.scheduler.service import SchedulerService

    await SchedulerService.tick()


@shared_task(name="run_autonomous_task_execution")  # type: ignore[reportCallIssue]
async def run_autonomous_task_execution(task_id: int, project_id: int | None = None):
    """
    Background task to execute an autonomous task.
    """
    from app.core.engine.background_agent import run_agent_background
    from app.core.environment.devices import DevicePool
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

            skill_ids = list(task.skill_ids or [])
            skills = []
            if skill_ids:
                from app.core.learning.skills.repository import skill_repository

                skills = await skill_repository.get_by_ids(skill_ids, db=session)

            intent_description = task.intent_description
            # 主 skill = 第一个（任务可关联多个 skill，主 skill 用于渲染初始 prompt）
            skill_name = skills[0].name if skills else ""
            skill_id = skills[0].id if skills else 0

        thread_id = f"auton-{task_id}-{int(time.time())}"

        from app.utils.template import render_template

        prompt = render_template(
            "core/engine/tasks/autonomous_task.prompt.j2",
            intent_description=intent_description,
            skill_name=skill_name,
            skill_id=skill_id,
            device_id=device_id,
        )

        # 2. Trigger Unified Dispatcher
        from app.core.engine.dispatch import dispatch_agent_run

        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=prompt,
            project_id=project_id if project_id is not None else DEFAULT_PROJECT_ID,
            metadata={
                "autonomous_task_id": task_id,
                "source_skill_id": skill_id,
                "device_id": device_id,
                "goal_prefix": "[Autonomous Task] ",
            },
        )

        if result.status == "failed":
            raise RuntimeError(f"Dispatch failed for task {task_id}: {result.error}")

        logger.info(f"[Task] Starting autonomous agent for task {task_id} on {device_id}")

        async with session_scope() as session:
            task = await session.get(AutonomousTask, task_id)
            if task:
                task.consecutive_failures = 0

        if result.inputs:
            await run_agent_background(thread_id, result.inputs)
    finally:
        await DevicePool.release_device(device_id, task_id=f"task-{task_id}")


# resolve_base_type, clean_none_values, distribute_list_to_schema_fields
# moved to app.utils.pydantic_helpers


async def run_engine_audit_structured_extraction(
    thread_id: str,
    project_id: int,
    member_id: int | None,
    run_id: str | None,
    summary: str,
    messages_dicts: list[dict],
    collected_schemas: list[dict],
    **kwargs,  # noqa: ARG001
):
    """
    Heavy reasoning extraction implementation.
    """
    import json

    from app.core.engine.event import (
        ExtractionCompletedEvent,
        ExtractionRequest,
    )
    from app.core.engine.extraction.schema import build_dynamic_schema
    from app.core.engine.message.converter import EvoMessageConverter
    from app.core.engine.message.native_classes import SystemMessage
    from app.core.events.base import system_bus
    from app.infrastructure.llm import InternalLLMService
    from app.utils.template import render_template

    if not collected_schemas:
        logger.info(f"[Task] No extraction schemas requested for thread {thread_id}, skipping extraction.")
        return

    requests = [ExtractionRequest(**s) for s in collected_schemas]
    DynamicVerdict = build_dynamic_schema(requests, include_base_fields=False)
    if not DynamicVerdict:
        return

    # Authoritatively repair the message history to ensure structural validity for strict LLM APIs
    messages = [m.model_dump() for m in EvoMessageConverter.repair(messages_dicts)]

    schema_json = json.dumps(
        DynamicVerdict.model_json_schema(), ensure_ascii=False, indent=2
    )

    extract_prompt = render_template(
        "core/memory/audit_extraction.prompt.j2",
        summary=summary,
        schema_json=schema_json,
    )

    try:
        response = await asyncio.wait_for(
            InternalLLMService.invoke_structured(
                messages=messages + [SystemMessage(content=extract_prompt).model_dump()],
                output_schema=DynamicVerdict,
                purpose="audit_extraction",
                temperature=0.1,
                max_tokens=4000,
                structured_output_method="function_calling",
                extra_body={"enable_thinking": False},
            ),
            timeout=300.0,
        )
        if response:
            extracted_data = response.model_dump()
            extracted_data.pop("summary", None)
            extracted_data.pop("is_completed", None)
            extracted_data = clean_none_values(extracted_data, DynamicVerdict)

            event = ExtractionCompletedEvent(
                thread_id=thread_id,
                project_id=project_id,
                member_id=member_id,
                run_id=run_id,
                extracted_data=extracted_data,
            )
            logger.info(f"[Task] 🚀 Publishing ExtractionCompletedEvent for thread {thread_id}")
            await system_bus.publish(event)
    except Exception as e:
        logger.exception(f"[Task] engine_audit_structured_extraction failed for thread {thread_id}: {e!r}")
        raise


@shared_task(name="engine_audit_structured_extraction")  # type: ignore[reportCallIssue]
async def engine_audit_structured_extraction(
    thread_id: str,
    project_id: int,
    member_id: int | None,
    run_id: str | None,
    summary: str,
    messages_dicts: list[dict],
    collected_schemas: list[dict],
    **kwargs,
):
    """
    Background Celery task that performs the heavy reasoning extraction (kimi-k2-thinking-turbo).
    """
    await run_engine_audit_structured_extraction(
        thread_id=thread_id,
        project_id=project_id,
        member_id=member_id,
        run_id=run_id,
        summary=summary,
        messages_dicts=messages_dicts,
        collected_schemas=collected_schemas,
        **kwargs,
    )


@shared_task(name="engine_run_agent_background")  # type: ignore[reportCallIssue]
async def run_agent_background_task(thread_id: str, inputs: dict):
    """
    Execute an agent run in the background (within Celery/Huey worker).
    """
    from app.core.engine.background_agent import run_agent_background

    await run_agent_background(thread_id, inputs)


@shared_task(name="engine_resume_graph_background")  # type: ignore[reportCallIssue]
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
