import asyncio
import json
import logging
import time
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field
from sqlalchemy import func, select

# Callbacks
from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.context.thread_store import thread_context_store
from app.core.engine.callbacks.database_logger import DatabaseCallbackHandler
from app.core.engine.callbacks.transparent import TransparentCallbackHandler
from app.core.evocloud import evocloud_manager
from app.core.evocloud.callback_handler import EvoCloudCallbackHandler
from app.core.exceptions import AgentCancelledException, AgentHumanInterruptException
# Graph
from app.core.globals import get_graph
from app.core.monitoring.activity import activity_monitor
from app.i18n.service import i18n
from app.infrastructure.cache import cache
from app.infrastructure.database.sql.database import session_scope
from app.models import Conversation, Message
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)

MAX_GOAL_LENGTH = 500


class BackgroundAgentInputs(BaseModel):
    """Structured inputs for background agent execution."""
    messages: list[dict] = Field(default_factory=list)
    project_id: int | None = None
    model: str | None = None
    goal: str = "处理用户请求"
    command_id: str | None = None
    checkpoint_id: str | None = None
    is_retry: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    iteration_count: int = 0
    hitl_resume_response: str | None = None
    session_goal: str | None = None


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


async def run_agent_background(thread_id: str, inputs: BackgroundAgentInputs | dict[str, Any]):
    """
    Background Task Logic (FastAPI BackgroundTasks).
    Replaces Celery task. Runs in the main event loop, reusing global resources.
    """
    if isinstance(inputs, dict):
        inputs = BackgroundAgentInputs(**inputs)

    try:
        # 1. Deserialize
        raw_messages = inputs.messages
        if raw_messages:
            raw_messages = _deserialize_messages(raw_messages)

        # Note: project_id can be 0 (global mode), so use get() without default
        project_id = inputs.project_id
        if project_id is None:
            project_id = DEFAULT_PROJECT_ID

        # 2. Context & DB Preparation (Parallelized)
        evoloop_command_id = inputs.command_id

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
        # _ensure_conversation_in_db expects a dict-like inputs with messages
        inputs_dict = inputs.model_dump()
        inputs_dict["messages"] = raw_messages
        setup_results = await asyncio.gather(
            _ensure_conversation_in_db(thread_id, project_id, inputs_dict),
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
                "model": inputs.model,  # User selected model (optional)
            },
            "metadata": {
                "project_id": project_id,
                "is_retry": inputs.is_retry,
                **inputs.metadata
            }
        }
        if inputs.checkpoint_id:
            config["configurable"]["checkpoint_id"] = inputs.checkpoint_id

        # Initialize Handlers
        callback = TransparentCallbackHandler(thread_id=thread_id)
        db_callback = DatabaseCallbackHandler(
            thread_id=thread_id,
            project_id=project_id,
            start_sequence=start_seq,
            run_id=run_id,
        )

        # Inject message_handler into config so nodes can report errors (e.g. QuotaExhaustedEvent)
        config["configurable"]["message_handler"] = db_callback._handler

        # 5. Execution
        # Start run with appropriate goal
        main_goal = inputs.goal
        await activity_monitor.start_run(thread_id, main_goal)
        logger.info(f"[BackgroundAgent] Started run for thread {thread_id} with goal: {main_goal}")

        # Memory Injection (Parallelized)
        from app.core.memory.lifespan import MemoryLifespanManager

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        memory_manager = container.memory_manager
        user_prefs, concepts_text = await asyncio.gather(
            memory_manager.get_merged_preferences("user_default", project_id=project_id),
            memory_manager.get_project_concepts(project_id)
        )
        inputs_dict["user_preferences"] = user_prefs
        inputs_dict["project_concepts"] = concepts_text

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
            input_payload: Any = inputs_dict

            # Ensure session_goal is present for all entry points (chat, retry, resume, webhook).
            # Prefer the explicitly passed session_goal; fallback to the first human message.
            if not inputs.session_goal and raw_messages:
                first_human = next(
                    (m for m in raw_messages if isinstance(m, HumanMessage)),
                    None,
                )
                if first_human:
                    raw_goal = first_human.content
                    if isinstance(raw_goal, list):
                        texts = [part.get("text", "") for part in raw_goal if isinstance(part, dict) and part.get("text")]
                        raw_goal = " ".join(texts).strip()
                    else:
                        raw_goal = str(raw_goal).strip()
                    if raw_goal:
                        # Truncate session_goal to keep it as a concise "Mission Anchor".
                        # This prevents massive logs/errors from bloating every turn and preserves token efficiency.
                        distilled_goal = raw_goal[:MAX_GOAL_LENGTH]
                        if len(raw_goal) > MAX_GOAL_LENGTH:
                            distilled_goal += "... (Full context available in history)"

                        input_payload["session_goal"] = distilled_goal
                        logger.info(f"[BackgroundAgent] Derived session_goal from first human message: {distilled_goal[:80]}...")
            elif inputs.session_goal:
                input_payload["session_goal"] = inputs.session_goal

            if inputs.hitl_resume_response is not None:
                user_response = inputs.hitl_resume_response

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

            # [MSG-TRACE] INPUT to graph
            if isinstance(input_payload, dict):
                _input_msgs = input_payload.get("messages", [])
                logger.info(f"[MSG-TRACE][background] GRAPH_INPUT messages: {len(_input_msgs)} msgs | types={[type(m).__name__ for m in _input_msgs]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in _input_msgs]} | contents={[str(getattr(m,'content',''))[:60] for m in _input_msgs]}")
            elif isinstance(input_payload, Command):
                _resume = getattr(input_payload, 'resume', None)
                logger.info(f"[MSG-TRACE][background] GRAPH_INPUT Command: resume_type={type(_resume).__name__} | resume_content={str(_resume)[:80] if _resume else 'None'}")
            else:
                logger.info(f"[MSG-TRACE][background] GRAPH_INPUT unknown type: {type(input_payload).__name__}")

            # Run Graph
            async for _event in graph_instance.astream(input_payload, config=config):
                await activity_monitor.check_cancellation(thread_id)
                pass

            # [MSG-TRACE] OUTPUT from checkpoint
            try:
                final_checkpoint_state = await graph_instance.aget_state(config)
                if final_checkpoint_state and final_checkpoint_state.values:
                    _final_msgs = final_checkpoint_state.values.get("messages", [])
                    logger.info(f"[MSG-TRACE][background] GRAPH_OUTPUT checkpoint.messages: {len(_final_msgs)} msgs | types={[type(m).__name__ for m in _final_msgs]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in _final_msgs]} | contents={[str(getattr(m,'content',''))[:60] for m in _final_msgs]}")
                else:
                    logger.info("[MSG-TRACE][background] GRAPH_OUTPUT checkpoint: no values")
            except Exception as e:
                logger.warning(f"[MSG-TRACE][background] Failed to read final checkpoint: {e}")

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
            from app.core.engine.events import AgentRunCompletedEvent
            from app.core.events import system_bus

            # We use the thread_id as the primary key for the learning trigger
            # goal can be reconstructed from the first message in the thread
            await system_bus.publish(AgentRunCompletedEvent(
                thread_id=thread_id,
                project_id=project_id,
                goal="Autonomous Task Execution", # Simplified goal for event
                status="done"
            ))
            logger.info(f"[BackgroundAgent] 📡 Published AgentRunCompletedEvent for thread {thread_id}")

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
    """Handle exceptions during graph execution using unified LLMErrorHandler."""
    from app.core.exceptions import AgentHumanInterruptException
    from app.models.schemas.events import QuotaExhaustedEvent
    from app.core.engine.error_handler import LLMErrorHandler

    # Check for context
    exc_name = type(e).__name__
    if isinstance(e, AgentHumanInterruptException) or "Interrupt" in exc_name or "GraphInterrupt" in exc_name:
        logger.info(f"Task {thread_id} interrupted for human input: {e}")
        return

    logger.error(f"Error running thread {thread_id}: {e}", exc_info=True)

    # 1. Classify the exception
    classification = LLMErrorHandler.classify_exception(e)
    error_type = classification.error_type

    # 2. Handle specific terminal errors with dedicated UI flows
    if error_type == "auth_expired":
        logger.warning(f"[EvoLoopAuth] Thread {thread_id} platform auth expired")
        await activity_monitor.end_run(thread_id, "failed")
        await cache.publish(
            f"chat:{thread_id}:events",
            json.dumps({
                "type": "auth_expired",
                "status": "auth_expired",
                "title": classification.title,
                "message": classification.message,
                "hint": classification.hint,
            })
        )
        return

    if error_type == "llm_auth":
        logger.warning(f"[LLMAuthError] Thread {thread_id} hit LLM API authentication error")
        await activity_monitor.end_run(thread_id, "failed")
        await cache.publish(
            f"chat:{thread_id}:events",
            json.dumps({
                "type": "llm_auth_error",
                "status": "failed",
                "title": classification.title,
                "message": classification.message,
                "hint": classification.hint,
            })
        )
        return

    if error_type == "quota_exhausted":
        logger.warning(f"[QuotaExhausted] Thread {thread_id} hit quota limit")
        await activity_monitor.end_run(thread_id, "quota_exhausted")
        await cache.publish(
            f"chat:{thread_id}:events",
            QuotaExhaustedEvent(
                type="quota_exhausted",
                title=classification.title,
                message=classification.message,
                hint=classification.hint,
                action_text=i18n.get('core_engine.quota_exhausted_action'),
            ).model_dump_json()
        )
        return

    # 3. Handle Retryable or Fatal errors
    await activity_monitor.end_run(thread_id, "failed")
    
    # Standard classification of "retryable" keywords
    is_retryable = error_type in ("rate_limit", "service_unavailable", "network_error")
    
    icon_warning = i18n.get('icons.warning') or '⚠️'
    icon_failed = i18n.get('icons.failed') or '❌'

    if is_retryable:
        user_message = (
            f"{icon_warning} **{classification.title}**: "
            f"{classification.message}\n\n"
            f"{classification.hint}\n\n"
            f"> {classification.raw_error[:200]}"
        )
        action_type = "warning"
    else:
        # Generic system/config error
        user_message = (
            f"{icon_failed} **{classification.title}**: "
            f"{classification.message}\n\n"
            f"{classification.hint}\n\n"
            f"> {classification.raw_error[:200]}"
        )
        action_type = "system"

    # Persist the failure message to DB for visibility and future learning (if applicable)
    await _persist_system_error(thread_id, project_id, user_message, action_type=action_type)


async def _persist_system_error(thread_id: str, project_id: int, error_details: str, action_type: str = "system"):
    """Save a system error message to the database.

    If the error is classified as ERROR_SYSTEM or AUTH_EXPIRED,
    it is NOT persisted (per MessageCategory design). These errors are
    infrastructure-level and provide no value for agent learning.
    """
    from app.core.messaging.category import MessageCategory
    from app.core.messaging.classifier import MessageClassifier

    # Classify the error content
    category = MessageClassifier.classify_ai_message(
        content=error_details,
        metadata={"is_error": True, "error_type": action_type}
    )

    # Skip persistence for system-level errors
    if category in (MessageCategory.ERROR_SYSTEM, MessageCategory.AUTH_EXPIRED):
        logger.debug(f"[_persist_system_error] Skipping persistence for {category} error")
        return

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
