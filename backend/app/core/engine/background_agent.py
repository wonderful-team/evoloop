import asyncio
import logging
import time
from typing import Any

# from celery import shared_task # Removed Celery
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from sqlalchemy import func, select

from app.core.callbacks.database_logger import DatabaseCallbackHandler
from app.core.callbacks.evoloop_logger import EvoLoopCallbackHandler

# Callbacks
from app.core.callbacks.transparent import TransparentCallbackHandler
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.context.thread_store import thread_context_store
from app.core.evocloud import evocloud_manager
from app.core.exceptions import AgentCancelledException, AgentHumanInterruptException

# Graph
from app.core.globals import get_graph
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.database.sql.database import session_scope
from app.models import Conversation, Message

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
            project_id = 1

        # 2. Context & DB Preparation (Parallelized)
        evoloop_command_id = inputs.get("command_id")

        async def get_max_seq():
            try:
                async with session_scope() as session:
                    stmt = select(func.max(Message.sequence_number)).where(Message.thread_id == thread_id)
                    result = await session.execute(stmt)
                    return result.scalar() or 0
            except Exception as e:
                logger.warning(f"Failed to fetch max sequence number: {e}")
                return 0

        # Run project setup, DB conversation check, sequence lookup, and Redis context load in parallel
        setup_results = await asyncio.gather(
            _ensure_conversation_in_db(thread_id, project_id, inputs),
            get_max_seq(),
            ContextManager.load_from_redis(thread_id) # Phase 4 Parallel context load
        )
        start_seq = setup_results[1]
        loaded_ctx = setup_results[2]

        # Project setup (needs result of thread_context_store and potentially loaded_ctx)
        working_dir = await _setup_project_context(thread_id, project_id, evoloop_command_id, loaded_ctx=loaded_ctx)

        # 3. Config Construction
        config = {
            "configurable": {
                "thread_id": thread_id,
                "working_directory": working_dir
            },
            "metadata": {
                "project_id": project_id,
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
            run_id=thread_id,
        )

        # 5. Execution
        await activity_monitor.start_run(thread_id)

        # Memory Injection (Parallelized)
        from app.core.memory import memory_manager

        user_prefs, concepts_text = await asyncio.gather(
            memory_manager.preferences.get_merged_preferences("user_default"),
            memory_manager.long_term.get_project_concepts(project_id)
        )
        inputs["user_preferences"] = user_prefs
        inputs["project_concepts"] = concepts_text

        try:
            callbacks = [callback, db_callback]
            callbacks.append(EvoLoopCallbackHandler(
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

            # Phase 4 Autonomy: Persist the subconscious Context Pool to Redis before exiting/suspending
            await ContextManager.save_to_redis(thread_id)

            # Snapshot & Finish
            activity_data = await activity_monitor.get_activity(thread_id)
            steps_snapshot = activity_data.get("steps", [])
            if steps_snapshot:
                await db_callback.snapshot_steps_to_last_message(steps_snapshot)

            # Phase 6: Give Celery tasks a moment to commit before frontend re-fetches history
            # This prevents a race condition where the 'finish' message is missing during re-fetch.
            await asyncio.sleep(1.0)
            await activity_monitor.end_run(thread_id, "done")

            # Phase 6: Publish AgentRunCompletedEvent for automated learning
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
        await _handle_task_exception(thread_id, project_id, e)


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
    from app.core.exceptions import AgentHumanInterruptException

    # Check for Interrupt
    exc_name = type(e).__name__

    # [HITL Fix] Explicitly catch our custom interrupt exception
    if isinstance(e, AgentHumanInterruptException) or "Interrupt" in exc_name or "GraphInterrupt" in exc_name:
        logger.info(f"Task {thread_id} interrupted for human input: {e}")

        # If it's our custom exception, we might have the request ID
        # req_id = getattr(e, "request_id", gen_uuid())

        # We don't need to create a NEW request if the exception came from tool execution
        # The tool already created it. We just set status.
        # But `set_human_request` updates Redis status.

        # If it is AgentHumanInterruptException, the tool already called activity_monitor.set_human_request
        # So we just need to ensure we don't overwrite it or fail.
        # However, the tool call might be inside a node. If we catch it here, the node failed.
        # Actually, LangGraph might handle exceptions differently.
        # If we raise BaseException, LangGraph usually stops.
        # We just need to mark run as "interrupted" in Redis (which the tool already did!)
        # So we simply return and DO NOT mark as failed.
        return

    logger.error(f"Error running thread {thread_id}: {e}", exc_info=True)
    await activity_monitor.end_run(thread_id, "failed")

    # Persist Error
    try:
        async with session_scope() as session:
            # Get next sequence
            stmt = select(func.max(Message.sequence_number)).where(Message.thread_id == thread_id)
            max_seq = (await session.execute(stmt)).scalar() or 0

            error_msg = Message(
                thread_id=thread_id,
                project_id=project_id,
                role="ai",
                content=f"❌ **System Error**: Agent execution failed.\n\nError Details:\n> {str(e)}\n\nPlease try again or contact support.",
                thinking="",
                sequence_number=max_seq + 1,
            )
            session.add(error_msg)
    except Exception as db_e:
        logger.error(f"Failed to persist error message: {db_e}")
