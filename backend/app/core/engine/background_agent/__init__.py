import asyncio
import json
import logging
import time
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

# Callbacks
from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.context.thread_store import thread_context_store
from app.core.engine.callbacks.database_logger import DatabaseCallbackHandler
from app.core.engine.callbacks.transparent import TransparentCallbackHandler
from app.core.evocloud import evocloud_manager
from app.core.exceptions import AgentCancelledException, AgentHumanInterruptException
# Graph
from app.core.globals import get_graph
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.database.sql.database import session_scope
from app.models import Conversation, Message
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)

MAX_GOAL_LENGTH = 500


class BackgroundAgentInputs(BaseModel):
    """Structured inputs for background agent execution.
    
    Uses extra='allow' so callers (e.g. API routes) can inject LangGraph state
    fields such as ``blackboard`` without modifying this schema.
    """
    model_config = ConfigDict(extra="allow")

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
    working_directory: str | None = None


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


async def _setup_project_context(
    thread_id: str,
    project_id: int | None,
    command_id: int | None = None,
    loaded_ctx: EvoContext | None = None,
    model: str | None = None,
    pre_resolved_dir: str | None = None
):
    """Initialize working directory and context vars."""
    if pre_resolved_dir:
        working_dir = pre_resolved_dir
        # Sync to thread store for consistency across system
        thread_context_store.set_working_directory(thread_id, working_dir)
    else:
        # Phase 2 Decoupling: Use API module directly
        # Note: project_id can be 0 (global mode) or None, both should skip project setup
        if project_id is not None and project_id != 0:
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
            active_model=model,
            command_id=command_id
        )
        ContextManager.set(ctx)
    else:
        # Update ephemeral request-scoped vars
        ctx.request_id = f"bg-{thread_id}-{int(time.time())}"
        ctx.working_directory = working_dir
        ctx.command_id = command_id
        ctx.active_model = model or ctx.active_model
        ContextManager.set(ctx)

    return working_dir


async def run_agent_background(thread_id: str, inputs: BackgroundAgentInputs | dict[str, Any]):
    """
    Background Task Logic (FastAPI BackgroundTasks).
    Replaces Celery task. Runs in the main event loop, reusing global resources.

    NOTE: Avoid calling this directly for new user-triggered turns. 
    Use `app.core.engine.dispatch.dispatch_agent_run` to ensure 
    DB persistence, context setup, and cloud sync are handled.
    """
    if isinstance(inputs, dict):
        inputs = BackgroundAgentInputs(**inputs)

    # Note: project_id can be 0 (global mode), so use get() without default
    project_id = inputs.project_id
    if project_id is None:
        project_id = DEFAULT_PROJECT_ID

    try:
        # 1. Deserialize
        raw_messages = inputs.messages
        if raw_messages:
            raw_messages = _deserialize_messages(raw_messages)

        # 2. Context & DB Preparation
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

        # Parallel context load
        loaded_ctx = await ContextManager.load(thread_id)

        # Project setup (needs result of thread_context_store and potentially loaded_ctx)
        working_dir = await _setup_project_context(
            thread_id,
            project_id,
            evoloop_command_id,
            loaded_ctx=loaded_ctx,
            model=inputs.model,
            pre_resolved_dir=inputs.working_directory
        )

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

        # 4. Prepare Workflow Inputs
        inputs_dict = inputs.model_dump()

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
            config["callbacks"] = callbacks
            config["recursion_limit"] = settings.RECURSION_LIMIT

            graph_instance = get_graph()
            if not graph_instance:
                raise ValueError("Global Graph not initialized")

            # [HITL Resume Logic]
            # Check if this is a resume request from Mobile/Background
            input_payload = inputs_dict

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
                        distilled_goal = raw_goal[:MAX_GOAL_LENGTH]
                        if len(raw_goal) > MAX_GOAL_LENGTH:
                            distilled_goal += "... (Full context available in history)"

                        input_payload["session_goal"] = distilled_goal
                        logger.info(f"[BackgroundAgent] Derived session_goal from first human message: {distilled_goal[:80]}...")
            elif inputs.session_goal:
                input_payload["session_goal"] = inputs.session_goal

            if inputs.hitl_resume_response is not None:
                from app.core.engine.background_agent.hitl import build_resume_command
                input_payload = await build_resume_command(
                    graph_instance, config, inputs.hitl_resume_response
                )

            # [MSG-TRACE] INPUT to graph
            from app.core.engine.nodes.utils import log_msg_trace
            if isinstance(input_payload, dict):
                _input_msgs = input_payload.get("messages", [])
                log_msg_trace("background", "GRAPH_INPUT", _input_msgs)
            elif hasattr(input_payload, "resume"):
                _resume = getattr(input_payload, 'resume', None)
                logger.info(f"[MSG-TRACE][background] GRAPH_INPUT Command: resume_type={type(_resume).__name__} | resume_content={str(_resume)[:80] if _resume else 'None'}")
            else:
                logger.info(f"[MSG-TRACE][background] GRAPH_INPUT unknown type: {type(input_payload).__name__}")

            # Run Graph
            async for _event in graph_instance.astream(input_payload, config=config):
                await activity_monitor.check_cancellation(thread_id)
                pass

            # [MSG-TRACE] OUTPUT from checkpoint
            _has_error_in_final_state = False
            try:
                final_checkpoint_state = await graph_instance.aget_state(config)
                if final_checkpoint_state and final_checkpoint_state.values:
                    _final_msgs = final_checkpoint_state.values.get("messages", [])
                    log_msg_trace("background", "GRAPH_OUTPUT", _final_msgs)

                    # Detect LLM errors that were swallowed as AIMessage(metadata={"is_error": True})
                    from langchain_core.messages import AIMessage
                    error_msgs = [
                        msg for msg in _final_msgs
                        if isinstance(msg, AIMessage) and getattr(msg, "metadata", {}).get("is_error")
                    ]
                    if error_msgs:
                        _has_error_in_final_state = True
                        last_error = error_msgs[-1]
                        error_content = str(last_error.content)
                        logger.warning(
                            f"[BackgroundAgent] Graph completed with embedded error: {error_content[:120]}..."
                        )

                        # Persist to DB so frontend can display it
                        from app.core.engine.background_agent.errors import persist_system_error
                        await persist_system_error(
                            thread_id, project_id, error_content, action_type="warning"
                        )

                        # Publish event to Redis
                        from app.infrastructure.cache import cache
                        await cache.publish(
                            f"chat:{thread_id}:events",
                            json.dumps({
                                "type": "warning",
                                "status": "failed",
                                "title": "请求失败",
                                "message": error_content,
                            })
                        )
                else:
                    logger.info("[MSG-TRACE][background] GRAPH_OUTPUT checkpoint: no values")
            except Exception as e:
                logger.warning(f"[MSG-TRACE][background] Failed to read final checkpoint: {e}")

            # Phase 4 Autonomy: Persist the subconscious Context Pool to cache before exiting/suspending
            await ContextManager.save(thread_id)

            # Snapshot & Finish - Save remaining steps to the final message
            activity_data = await activity_monitor.get_activity(thread_id)
            steps_snapshot = activity_data.get("steps", [])
            if steps_snapshot:
                remaining_steps = steps_snapshot[db_callback._last_attributed_step_index:]
                if remaining_steps:
                    await db_callback.snapshot_steps_to_last_message(remaining_steps)

            await activity_monitor.end_run(thread_id, "done")

            # Publish AgentRunCompletedEvent for automated learning
            from app.core.engine.events import AgentRunCompletedEvent
            from app.core.events import system_bus

            await system_bus.publish(AgentRunCompletedEvent(
                thread_id=thread_id,
                project_id=project_id,
                goal="Autonomous Task Execution", # Simplified goal for event
                status="done"
            ))
            logger.info(f"[BackgroundAgent] 📡 Published AgentRunCompletedEvent for thread {thread_id}")

            # 最终同步：发送所有消息 + command_complete 信号到 Gateway
            try:
                from app.core.engine.message.sync_coordinator import get_sync_coordinator
                coordinator = get_sync_coordinator()
                await coordinator.sync_final(thread_id, evoloop_command_id)
            except Exception as sync_e:
                logger.warning(f"[BackgroundAgent] Final sync failed: {sync_e}")

        except AgentCancelledException:
            logger.info(f"Task {thread_id} cancelled by user.")
            await activity_monitor.end_run(thread_id, "cancelled")

        except AgentHumanInterruptException:
            logger.info(f"[BackgroundAgent] Task {thread_id} interrupted for human input. Run status: interrupted")

        except Exception as e:
            err_msg = str(e)
            if "recursion limit" in err_msg.lower():
                logger.error(f"Thread {thread_id} hit recursion limit: {e}")
                await activity_monitor.end_run(thread_id, "failed")
                from app.core.engine.background_agent.errors import persist_system_error
                await persist_system_error(thread_id, project_id, "Recursion limit exceeded. The agent may be stuck in a loop.")
            else:
                from app.core.engine.background_agent.errors import handle_task_exception
                await handle_task_exception(thread_id, project_id, e)

    except Exception as e:
        logger.error(f"Fatal error during agent preparation for {thread_id}: {e}", exc_info=True)
        await activity_monitor.end_run(thread_id, "failed")
        from app.core.engine.background_agent.errors import persist_system_error
        await persist_system_error(thread_id, project_id, f"Preparation failed: {str(e)}")
