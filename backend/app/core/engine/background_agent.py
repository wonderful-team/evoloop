import asyncio
import logging
import time
from typing import Any

# from celery import shared_task # Removed Celery
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from sqlalchemy import func, select

from app.core.callbacks.database_logger import DatabaseCallbackHandler
from app.core.evocloud.callback_handler import EvoCloudCallbackHandler

# Callbacks
from app.constants import DEFAULT_PROJECT_ID
from app.core.callbacks.transparent import TransparentCallbackHandler
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.context.thread_store import thread_context_store
from app.core.evocloud import evocloud_manager
from app.core.exceptions import AgentCancelledException, AgentHumanInterruptException
from app.i18n.service import i18n

# Graph
from app.core.globals import get_graph
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.cache import cache
from app.infrastructure.database.sql.database import session_scope
from app.models import Conversation, Message
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


def _deserialize_messages(raw_messages: list[Any]) -> list[BaseMessage]:
    """Ensure messages are valid LangChain objects."""
    deserialized = []
    for m in raw_messages:
        if isinstance(m, dict):
            if m.get("type") == "human":
                deserialized.append(HumanMessage(content=m.get("content", "")))
            else:
                deserialized.append(m)  # Assume other dicts are handled or already compatible?
        else:
            deserialized.append(m)
    return deserialized


async def _setup_project_context(thread_id: str, project_id: int | None, command_id: int | None = None, loaded_ctx: EvoContext | None = None):
    """Initialize working directory and context vars."""
    # Phase 2 Decoupling: Use API module directly
    # Note: project_id can be 0 (global mode) or None, both should skip project setup
    if project_id is not None and project_id != 0:
        from app.core.evocloud import evocloud_manager
        project = await evocloud_manager.get_project_by_id(project_id)
        if project and project.get("path"):
            thread_context_store.set_working_directory(thread_id, project["path"])

    working_dir = thread_context_store.get_working_directory(thread_id)

    # Phase 4 Autonomy: Use pre-loaded context from parallel gather
    ctx = loaded_ctx
    if not ctx:
        # Initialize Core Context
        ctx = EvoContext(
            request_id=f"bg-{thread_id}-{int(time.time())}",
            thread_id=thread_id,
            project_id=project_id,
            working_directory=working_dir,
            command_id=command_id
        )
        ContextManager.set(ctx)
    else:
        # Update ephemeral request-scoped vars
        ctx.request_id = f"bg-{thread_id}-{int(time.time())}"
        ctx.working_directory = working_dir
        ctx.command_id = command_id
        ContextManager.set(ctx)

    return working_dir


async def _ensure_conversation_in_db(thread_id: str, project_id: int, inputs: dict[str, Any]):
    """Create conversation record if missing."""
    try:
        async with session_scope() as session:
            conversation = await session.get(Conversation, thread_id)
            if not conversation:
                conversation_title = "New Conversation"
                if inputs.get("task_title"):
                    conversation_title = inputs["task_title"]
                elif inputs.get("messages") and inputs["messages"]:
                    try:
                        first_msg = inputs["messages"][0]
                        conversation_title = first_msg.content[:50]
                    except Exception:
                        pass

                conversation = Conversation(
                    id=thread_id,
                    project_id=project_id,
                    title=conversation_title
                )
                session.add(conversation)
    except Exception as e:
        logger.error(f"Failed to ensure conversation {thread_id}: {e}")


async def run_agent_background(thread_id: str, inputs: dict[str, Any]):
    """
    Background Task Logic (FastAPI BackgroundTasks).
    Replaces Celery task. Runs in the main event loop, reusing global resources.
    """
    try:
        # 1. Deserialize
        if "messages" in inputs:
            inputs["messages"] = _deserialize_messages(inputs["messages"])

        inputs["iteration_count"] = inputs.get("iteration_count", 0)
        # Note: project_id can be 0 (global mode), so use get() without default
        project_id = inputs.get("project_id")
        if project_id is None:
            project_id = DEFAULT_PROJECT_ID

        # 2. Context & DB Preparation (Parallelized)
        evoloop_command_id = inputs.get("command_id")

        # Fetch max sequence number
        start_seq = 0
        try:
            async with session_scope() as session:
                stmt = select(func.max(Message.sequence_number)).where(Message.thread_id == thread_id)
                result = await session.execute(stmt)
                start_seq = result.scalar() or 0
        except Exception as e:
            logger.warning(f"Failed to fetch max sequence number: {e}")

        # Run project setup, DB conversation check, and cache context load in parallel
        setup_results = await asyncio.gather(
            _ensure_conversation_in_db(thread_id, project_id, inputs),
            ContextManager.load_from_redis(thread_id) # Phase 4 Parallel context load
        )
        loaded_ctx = setup_results[1]

        # Project setup (needs result of thread_context_store and potentially loaded_ctx)
        working_dir = await _setup_project_context(thread_id, project_id, evoloop_command_id, loaded_ctx=loaded_ctx)

        # 3. Config Construction
        run_id = f"run-{gen_uuid()[:8]}"
        config = {
            "configurable": {
                "thread_id": thread_id,
                "working_directory": working_dir,
                "run_id": run_id, # Track the specific run attempt
                "model": inputs.get("model"),  # User selected model (optional)
            },
            "metadata": {
                "project_id": project_id,
                "is_retry": inputs.get("is_retry", False),
                **(inputs.get("metadata", {}))
            }
        }
        if inputs.get("checkpoint_id"):
            config["configurable"]["checkpoint_id"] = inputs["checkpoint_id"]

        # Initialize Handlers
        callback = TransparentCallbackHandler(thread_id=thread_id)
        db_callback = DatabaseCallbackHandler(
            thread_id=thread_id,
            project_id=project_id,
            start_sequence=start_seq,
            run_id=run_id,
        )

        # 5. Execution
        # Start run with appropriate goal
        main_goal = inputs.get("goal", "处理用户请求")
        await activity_monitor.start_run(thread_id, main_goal)
        logger.info(f"[BackgroundAgent] Started run for thread {thread_id} with goal: {main_goal}")

        # Memory Injection (Parallelized)
        from app.core.memory.lifespan import MemoryLifespanManager
        
        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        memory_manager = container.memory_manager
        user_prefs, concepts_text = await asyncio.gather(
            memory_manager.preferences.get_merged_preferences("user_default"),
            memory_manager.long_term.get_project_concepts(project_id)
        )
        inputs["user_preferences"] = user_prefs
        inputs["project_concepts"] = concepts_text

        try:
            callbacks = [callback, db_callback]
            callbacks.append(EvoCloudCallbackHandler(
                evocloud_manager,
                thread_id,
                project_id=project_id,
                command_id=evoloop_command_id
            ))

            config["callbacks"] = callbacks
            config["recursion_limit"] = settings.RECURSION_LIMIT

            graph_instance = get_graph()
            if not graph_instance:
                raise ValueError("Global Graph not initialized")

            # [HITL Resume Logic]
            # Check if this is a resume request from Mobile/Background
            input_payload = inputs
            if "hitl_resume_response" in inputs:
                user_response = inputs["hitl_resume_response"]

                # Check state to see if we need to satisfy a specific tool call
                current_state = await graph_instance.aget_state(config)
                last_tool_call_id = None

                if current_state.values and "messages" in current_state.values:
                    history = current_state.values["messages"]
                    if history:
                        last_msg = history[-1]
                        # Check for pending tool calls
                        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                            last_tool_call = last_msg.tool_calls[-1]
                            if last_tool_call["name"] in ["request_approval", "request_human_input"]:
                                logger.info(f"Background Resume: Auto-completing tool {last_tool_call['name']}")
                                last_tool_call_id = last_tool_call["id"]

                # Construct Command
                if last_tool_call_id:
                    # Resume with Tool Message
                    tool_msg = ToolMessage(
                        tool_call_id=last_tool_call_id,
                        content=str(user_response),
                    )
                    input_payload = Command(resume=tool_msg)
                else:
                    # Fallback or standard resume
                    input_payload = Command(resume=user_response)

            # Run Graph
            async for _event in graph_instance.astream(input_payload, config=config):
                await activity_monitor.check_cancellation(thread_id)
                pass

            # Phase 4 Autonomy: Persist the subconscious Context Pool to cache before exiting/suspending
            await ContextManager.save_to_redis(thread_id)

            # Snapshot & Finish - Save remaining steps to the final message
            # Note: Most steps have already been attributed to intermediate messages
            # via _attribute_pending_steps_to_previous_message. Only the steps
            # since the last AI message need to be saved here.
            activity_data = await activity_monitor.get_activity(thread_id)
            steps_snapshot = activity_data.get("steps", [])
            if steps_snapshot:
                # Get the remaining steps that haven't been attributed yet
                remaining_steps = steps_snapshot[db_callback._last_attributed_step_index:]
                if remaining_steps:
                    await db_callback.snapshot_steps_to_last_message(remaining_steps)

            # [PERFORMANCE FIX] Optimized delay for message persistence:
            # - EMBEDDED_MODE: snapshot_steps_to_last_message already awaits task completion (result.get())
            #   so no additional delay needed
            # - Non-embedded: Celery tasks are fire-and-forget, need minimal buffer for DB consistency
            # Reduced from 1.0s to 0.2s based on actual profiling (Celery task completion <100ms typical)
            if not settings.EMBEDDED_MODE:
                await asyncio.sleep(0.2)
            
            await activity_monitor.end_run(thread_id, "done")

            # Publish AgentRunCompletedEvent for automated learning
            try:
                from app.core.events import system_bus
                from app.core.events.agent import AgentRunCompletedEvent
                
                # We use the thread_id as the primary key for the learning trigger
                # goal can be reconstructed from the first message in the thread
                await system_bus.publish(AgentRunCompletedEvent(
                    thread_id=thread_id,
                    project_id=project_id,
                    goal="Autonomous Task Execution", # Simplified goal for event
                    status="done"
                ))
                logger.info(f"[BackgroundAgent] 📡 Published AgentRunCompletedEvent for thread {thread_id}")
            except Exception as e:
                logger.warning(f"[BackgroundAgent] Failed to publish run completion event: {e}")

            # Upload Log
            await _upload_final_log(graph_instance, config, thread_id, evoloop_command_id, project_id)

        except AgentCancelledException:
            logger.info(f"Task {thread_id} cancelled by user.")
            await activity_monitor.end_run(thread_id, "cancelled")

        except AgentHumanInterruptException:
            # HITL interrupt is expected - the tool already created the request
            # and set the run status to 'interrupted'. We just let the run end gracefully.
            logger.info(f"[BackgroundAgent] Task {thread_id} interrupted for human input. Run status: interrupted")
            # No need to call end_run - the tool already set status via activity_monitor.set_human_request

        except Exception as e:
            # Catch recursion limit errors or other graph execution failures
            err_msg = str(e)
            if "recursion limit" in err_msg.lower():
                logger.error(f"Thread {thread_id} hit recursion limit: {e}")
                await activity_monitor.end_run(thread_id, "failed")
                await _persist_system_error(thread_id, project_id, "Recursion limit exceeded. The agent may be stuck in a loop.")
            else:
                await _handle_task_exception(thread_id, project_id, e)

    except Exception as e:
        # Preparation failures (DB, Context, etc.)
        logger.error(f"Fatal error during agent preparation for {thread_id}: {e}", exc_info=True)
        await activity_monitor.end_run(thread_id, "failed")
        await _persist_system_error(thread_id, project_id, f"Preparation failed: {str(e)}")


async def _upload_final_log(graph, config, thread_id, command_id, project_id):
    try:
        final_state = await graph.aget_state(config)
        if final_state.values and "messages" in final_state.values:
            messages = final_state.values["messages"]
            if messages:
                last_msg = messages[-1]
                if hasattr(last_msg, "content") and last_msg.content:
                    content = last_msg.content

                    # Upload to debug logs (for trace viewing)
                    await evocloud_manager.upload_log(
                        thread_id=thread_id,
                        log_type="model",
                        content=content,
                        command_id=command_id,
                        project_id=project_id,
                    )
    except Exception as e:
        logger.warning(f"Failed to send final output: {e}")


async def _handle_task_exception(thread_id: str, project_id: int, e: Exception):
    """Handle exceptions during graph execution (Phase 5: Global Error Boundaries)."""
    from app.core.exceptions import AgentHumanInterruptException
    from app.models.schemas.events import QuotaExhaustedEvent

    # Check for context
    exc_name = type(e).__name__
    error_str = str(e).lower()

    if isinstance(e, AgentHumanInterruptException) or "Interrupt" in exc_name or "GraphInterrupt" in exc_name:
        logger.info(f"Task {thread_id} interrupted for human input: {e}")
        return

    logger.error(f"Error running thread {thread_id}: {e}", exc_info=True)
    
    # 1. Distinguish between Retryable, Quota Exhausted, and Fatal Errors
    is_quota_exhausted = "quota_exhausted" in error_str or "insufficient quota" in error_str
    is_retryable = any(kw in error_str for kw in [
        "timeout", "rate limit", "connection error", "api_error", 
        "unavailable", "overloaded", "socket", "httpx"
    ])
    
    # 2. Handle Quota Exhausted - Special flow
    if is_quota_exhausted:
        logger.warning(f"[QuotaExhausted] Thread {thread_id} hit quota limit")
        
        # Set special status (does not pollute message history)
        await activity_monitor.end_run(thread_id, "quota_exhausted")
        
        # Publish special event for UI
        await cache.publish(
            f"chat:{thread_id}:events",
            QuotaExhaustedEvent(
                type="quota_exhausted",
                title=i18n.get('core_engine.quota_exhausted_title'),
                message=i18n.get('core_engine.quota_exhausted_desc'),
                hint=i18n.get('core_engine.quota_exhausted_hint'),
                action_text=i18n.get('core_engine.quota_exhausted_action'),
            ).model_dump_json()
        )
        return
    
    # 3. Handle other errors
    await activity_monitor.end_run(thread_id, "failed")
    
    if is_retryable:
        user_message = (
            f"{i18n.get('icons.warning')} **{i18n.get('core_engine.retryable_error_title')}**: "
            f"{i18n.get('core_engine.retryable_error_desc')}\n\n"
            f"> {str(e)}\n\n"
            f"I have paused execution to prevent state corruption. You can try to **Resume** this task."
        )
        action_type = "warning"
    else:
        user_message = (
            f"{i18n.get('icons.failed')} **{i18n.get('core_engine.system_error_title')}**: "
            f"{i18n.get('core_engine.execution_failed')}\n\n"
            f"{i18n.get('core_engine.error_details')}:\n> {str(e)}\n\n"
            f"{i18n.get('core_engine.retry_prompt')}"
        )
        action_type = "system"

    # 4. Persist to DB
    await _persist_system_error(thread_id, project_id, user_message, action_type=action_type)


async def _persist_system_error(thread_id: str, project_id: int, error_details: str, action_type: str = "system"):
    """Save a system error message to the database."""
    try:
        async with session_scope() as session:
            # Get next sequence
            stmt = select(func.max(Message.sequence_number)).where(Message.thread_id == thread_id)
            max_seq = (await session.execute(stmt)).scalar() or 0

            error_msg = Message(
                thread_id=thread_id,
                project_id=project_id,
                role="ai",
                action_type=action_type,
                content=error_details,
                sequence_number=max_seq + 1
            )
            session.add(error_msg)
    except Exception as db_e:
        logger.error(f"Failed to persist error message: {db_e}")
