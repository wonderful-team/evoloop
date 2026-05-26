import asyncio
import logging
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Callbacks
from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.context.thread_store import thread_context_store
from app.core.engine.callbacks.database_logger import DatabaseCallbackHandler
from app.core.engine.callbacks.transparent import TransparentCallbackHandler
from app.core.engine.message.converter import EvoMessageConverter
from app.core.exceptions import AgentCancelledException, AgentHumanInterruptException
# Graph
from app.core.globals import get_graph
from app.core.monitoring.activity import activity_monitor
from app.core.engine.background_agent.errors import handle_task_exception
from app.core.engine.background_agent.hitl import build_resume_command

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
    command_id: str | int | None = None
    checkpoint_id: str | None = None
    is_retry: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    iteration_count: int = 0
    hitl_resume_response: str | None = None
    session_goal: str | None = None
    working_directory: str | None = None


async def run_agent_background(thread_id: str, inputs: BackgroundAgentInputs | dict[str, Any]):
    """
    Background Task Logic (FastAPI BackgroundTasks).
    Replaces Celery task. Runs in the main event loop, reusing global resources.
    """
    if isinstance(inputs, dict):
        inputs = BackgroundAgentInputs(**inputs)

    # Note: project_id can be 0 (global mode), so use get() without default
    project_id = inputs.project_id
    if project_id is None:
        project_id = DEFAULT_PROJECT_ID

    # 1. Lifecycle & Context Management
    task_type = inputs.metadata.get("task_type") if inputs.metadata else None
    async with activity_monitor.run_scope(thread_id, inputs.goal, task_type=task_type) as run_id:
        _final_status = "done"  # Track final status for command_complete signal
        try:
            # 2. Deserialize & Prepare
            raw_messages = EvoMessageConverter.to_langchain(inputs.messages)

            # Parallel context load
            loaded_ctx = await ContextManager.load(thread_id)

            # Setup initial context
            ctx = loaded_ctx
            working_dir = inputs.working_directory
            if not working_dir:
                working_dir = thread_context_store.get_working_directory(thread_id)

            if not ctx:
                ctx = EvoContext(
                    thread_id=thread_id,
                    project_id=project_id,
                    working_directory=working_dir,
                    active_model=inputs.model,
                    command_id=inputs.command_id
                )
            else:
                ctx.request_id = f"bg-{thread_id}-{int(time.time())}"
                ctx.working_directory = working_dir
                ctx.command_id = inputs.command_id
                ctx.active_model = inputs.model or ctx.active_model
            
            # Allow tests/metadata to inject user_id for benefit-gated tools
            if not ctx.user_id and inputs.metadata.get("user_id"):
                ctx.user_id = inputs.metadata["user_id"]
                
            ContextManager.set(ctx)

            # Trigger Event-Driven Context Hydration
            from app.core.engine.event.publishers import publish_agent_session_started
            await publish_agent_session_started(thread_id=thread_id, project_id=project_id)
            
            # The hydrator might have updated the working_dir in context
            ctx = ContextManager.current()
            working_dir = ctx.working_directory

            # 3. Config Construction
            config: dict[str, Any] = {
                "configurable": {
                    "thread_id": thread_id,
                    "working_directory": working_dir,
                    "run_id": run_id,
                    "model": inputs.model,
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
            
            # Message management handler (handles persistence and streaming)
            # We always initialize it to ensure UI streaming works even if DB persistence is skipped.
            db_callback = DatabaseCallbackHandler(
                thread_id=thread_id,
                project_id=project_id,
                run_id=run_id,
            )
            config["configurable"]["message_handler"] = db_callback._handler

            # 4. Prepare Workflow Inputs
            inputs_dict = inputs.model_dump()
            
            # Instantiate Blackboard
            from app.core.engine.state.blackboard import BlackboardState
            if "blackboard" not in inputs_dict:
                inputs_dict["blackboard"] = BlackboardState().model_dump()
            
            blackboard = BlackboardState.model_validate(inputs_dict["blackboard"])
            
            # Extract last human msg for predictive memory
            from app.core.engine.message.utils import get_last_human_message
            last_human_msg = get_last_human_message(raw_messages) or ""

            # Unified Context Hydration (Runs ONCE per session)
            from app.core.memory.hydrator import AgentContextHydrator
            await AgentContextHydrator.hydrate(
                ctx=ctx,
                blackboard=blackboard,
                config=config,  # type: ignore[arg-type]
                last_human_msg=last_human_msg,
                is_retry=inputs.is_retry,
                is_subtask=False,
                iteration_count=inputs.iteration_count
            )
            
            # Update inputs with hydrated blackboard
            inputs_dict["blackboard"] = blackboard.model_dump()

            # 5. Execution Setup
            callbacks = [callback]
            if db_callback:
                callbacks.append(db_callback)
            config["callbacks"] = callbacks

            config["recursion_limit"] = settings.RECURSION_LIMIT

            graph_instance = get_graph()
            if not graph_instance:
                raise ValueError("Global Graph not initialized")

            input_payload = inputs_dict
            
            # 5.5 Authoritative session_goal distillation
            from app.core.engine.message.goal_distiller import GoalDistiller
            input_payload["session_goal"] = GoalDistiller.resolve(
                explicit_goal=inputs.session_goal,
                messages=raw_messages
            )

            if inputs.hitl_resume_response is not None:
                input_payload = await build_resume_command(graph_instance, config, inputs.hitl_resume_response)

            # 6. Run Graph
            async for _event in graph_instance.astream(input_payload, config=config):
                await activity_monitor.check_cancellation(thread_id)

            # 7. Finalize Run
            await ContextManager.save(thread_id)

        except AgentCancelledException:
            # Expected control flow: user stopped the run.
            # run_scope has already handled cleanup/logging.
            _final_status = "cancelled"
            return
        except AgentHumanInterruptException:
            # Expected control flow: agent is waiting for human input.
            # Do NOT send command_complete — the task is paused, not finished.
            return
        except Exception as e:
            # Let handle_task_exception deal with DB/UI reporting.
            # It already persists the error, pushes to UI/Mobile, and calls
            # activity_monitor.end_run with the appropriate status.
            handler = db_callback._handler if db_callback else None
            await handle_task_exception(thread_id, project_id, e, handler=handler)

            # Do not re-raise. The final status (failed, quota_exhausted, etc.)
            # is already set. Re-raising would only cause run_scope to
            # redundantly call end_run and propagate the exception to
            # FastAPI BackgroundTasks with no benefit.
            return
