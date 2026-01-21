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
from app.core.exceptions import AgentCancelledException

# Graph
from app.core.globals import get_graph
from app.core.monitoring.activity import activity_monitor
from app.domain.project.service import project_context_manager
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import Conversation, Message
from app.infrastructure.external.evocloud import evocloud_client
import logging
logger = logging.getLogger(__name__)

# Utils
from app.utils.context import set_context


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


async def _setup_project_context(thread_id: str, project_id: int):
    """Initialize working directory and context vars."""
    project = await project_context_manager.get_project_by_id(project_id)
    if project and project.get("path"):
        project_context_manager.set_working_directory(thread_id, project["path"])

    working_dir = project_context_manager.get_working_directory(thread_id)
    set_context(thread_id=thread_id, project_id=project_id, working_directory=working_dir)
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
        project_id = inputs.get("project_id", 1)

        # 2. Context Setup
        working_dir = await _setup_project_context(thread_id, project_id)

        # 3. Config Construction
        config = {
            "configurable": {
                "thread_id": thread_id,
                "working_directory": working_dir
            },
            "metadata": {
                "project_id": project_id
            }
        }
        if inputs.get("checkpoint_id"):
            config["configurable"]["checkpoint_id"] = inputs["checkpoint_id"]

        evoloop_command_id = inputs.get("command_id")

        # 4. Callbacks & DB Init
        # Ensure Conversation Exists
        await _ensure_conversation_in_db(thread_id, project_id, inputs)

        # Get Start Sequence
        start_seq = 0
        try:
            async with session_scope() as session:
                stmt = select(func.max(Message.sequence_number)).where(Message.thread_id == thread_id)
                result = await session.execute(stmt)
                max_seq = result.scalar()
                if max_seq is not None:
                    start_seq = max_seq
        except Exception as e:
            logger.warning(f"Failed to fetch max sequence number: {e}")

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

        # Memory Injection
        from app.domain.memory.service import memory_service

        user_prefs = await memory_service.get_user_preferences("user_default")
        concepts_text = await memory_service.search_concepts("", project_id)
        inputs["user_preferences"] = user_prefs
        inputs["project_concepts"] = concepts_text

        try:
            callbacks = [callback, db_callback]
            callbacks.append(EvoLoopCallbackHandler(evocloud_client, thread_id, command_id=evoloop_command_id))

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
                            if last_tool_call["name"] in [
                                "request_approval",
                                "request_human_input",
                            ]:
                                logger.info(
                                    f"Background Resume: Auto-completing tool {last_tool_call['name']}"
                                )
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

            # Snapshot & Finish
            activity_data = await activity_monitor.get_activity(thread_id)
            steps_snapshot = activity_data.get("steps", [])
            if steps_snapshot:
                await db_callback.snapshot_steps_to_last_message(steps_snapshot)

            await activity_monitor.end_run(thread_id, "done")

            # Upload Log
            await _upload_final_log(graph_instance, config, thread_id, evoloop_command_id)

        except AgentCancelledException:
            logger.info(f"Task {thread_id} cancelled by user.")
            await activity_monitor.end_run(thread_id, "cancelled")

    except Exception as e:
        await _handle_task_exception(thread_id, project_id, e)


async def _upload_final_log(graph, config, thread_id, command_id):
    try:
        final_state = await graph.aget_state(config)
        if final_state.values and "messages" in final_state.values:
            messages = final_state.values["messages"]
            if messages:
                last_msg = messages[-1]
                if hasattr(last_msg, "content") and last_msg.content:
                    await evocloud_client.upload_log(
                        thread_id=thread_id,
                        log_type="output",
                        content=last_msg.content,
                        command_id=command_id,
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
