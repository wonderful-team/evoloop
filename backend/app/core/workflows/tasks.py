
import asyncio
import logging
from typing import Dict, Any, List

from celery import shared_task
from app.celery_app import celery_app
from langchain_core.messages import HumanMessage, BaseMessage
from app.logging import logger, set_context
from app.core.config import settings
from app.domain.project.service import project_context_manager
from app.infrastructure.database.sql.models import Conversation
from app.infrastructure.database.sql.database import session_scope

# Callbacks
from app.core.callbacks.transparent import TransparentCallbackHandler
from app.core.callbacks.database_logger import DatabaseCallbackHandler
from app.core.callbacks.evoloop_logger import EvoLoopCallbackHandler
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.external.imagicbox import imagicbox_client

# Graph
from app.core.globals import get_graph

logger = logging.getLogger(__name__)

async def _run_agent_logic(thread_id: str, inputs: Dict[str, Any]):
    """
    Async logic for running the agent.
    """
    # 1. Deserialize Messages if needed
    # Ensure messages are objects, not dicts (if serialized for Celery)
    if "messages" in inputs:
        deserialized_msgs = []
        for m in inputs["messages"]:
            if isinstance(m, dict):
                # Simple Manual Reconstruction to avoid pickle issues
                if m.get("type") == "human":
                    deserialized_msgs.append(HumanMessage(content=m.get("content", "")))
                # Add other types if needed
            else:
                deserialized_msgs.append(m)
        inputs["messages"] = deserialized_msgs

    # Ensure iteration_count is initialized for state graph
    inputs["iteration_count"] = inputs.get("iteration_count", 0)

    project_id = inputs.get("project_id", 1)
    
    # Context Setup
    project = await project_context_manager.get_project_by_id(project_id)
    if project and project.get("path"):
        project_context_manager.set_working_directory(thread_id, project["path"])
    
    working_dir = project_context_manager.get_working_directory(thread_id)
    set_context(thread_id=thread_id, project_id=project_id, working_directory=working_dir)
    
    # 2. Config
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
    
    # Callbacks
    callback = TransparentCallbackHandler(thread_id=thread_id)
    db_callback = DatabaseCallbackHandler(thread_id=thread_id, project_id=project_id)
    
    await activity_monitor.start_run(thread_id)
    
    # Ensure Conversation Exists
    try:
        async with session_scope() as session:
            conversation = await session.get(Conversation, thread_id)
            if not conversation:
                conversation_title = "New Conversation"
                if inputs.get("task_title"):
                     conversation_title = inputs["task_title"]
                elif inputs.get("messages") and inputs["messages"]:
                     first_msg = inputs["messages"][0]
                     conversation_title = first_msg.content[:50]
                
                conversation = Conversation(
                    id=thread_id,
                    project_id=project_id,
                    title=conversation_title
                )
                session.add(conversation)
    except Exception as e:
        logger.error(f"Failed to ensure conversation {thread_id}: {e}")

    # Memory Injection
    from app.domain.memory.service import memory_service
    user_prefs = await memory_service.get_user_preferences("user_default")
    concepts_text = await memory_service.search_concepts("", project_id)
    inputs["user_preferences"] = user_prefs
    inputs["project_concepts"] = concepts_text

    try:
        callbacks = [callback, db_callback]
        callbacks.append(EvoLoopCallbackHandler(imagicbox_client, thread_id, command_id=evoloop_command_id))
            
        config["callbacks"] = callbacks
        config["recursion_limit"] = 50
        
        # MCP Connection (Per-Task to ensure loop binding)
        # We must connect here because Celery worker process is distinct and loop might change
        from app.infrastructure.mcp.client import mcp_client_manager
        
        try:
            await mcp_client_manager.connect_all()
            
            # Per-Task Graph Initialization
            # We initialize the DB Pool and Graph here to ensure they are bound to the current event loop
            # and to avoid global state issues in the Celery worker process.
            from psycopg_pool import AsyncConnectionPool
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from app.core.workflows.workflow import create_graph
            from app.core.config import settings
    
            db_uri = settings.CHECKPOINTER_DATABASE_URI
            # kwargs={"autocommit": True} is required for CREATE INDEX CONCURRENTLY
            async with AsyncConnectionPool(conninfo=db_uri, max_size=5, kwargs={"autocommit": True}) as db_pool:
                checkpointer = AsyncPostgresSaver(db_pool)
                await checkpointer.setup()
                
                graph_instance = create_graph(checkpointer=checkpointer)
                
                # Run Graph
                async for event in graph_instance.astream(inputs, config=config):
                    pass
                
            await activity_monitor.end_run(thread_id, "done")
            
            # Upload Final Log
            try:
                final_state = await graph_instance.aget_state(config)
                if final_state.values and "messages" in final_state.values:
                    messages = final_state.values["messages"]
                    if messages:
                        last_msg = messages[-1]
                        if hasattr(last_msg, "content") and last_msg.content:
                            await imagicbox_client.upload_log(
                                thread_id=thread_id,
                                log_type="output", 
                                content=last_msg.content,
                                command_id=evoloop_command_id
                            )
            except Exception as e:
                logger.warning(f"Failed to send final output: {e}")
                
        finally:
            # Cleanup MCP subprocesses
            await mcp_client_manager.cleanup()
        
    except Exception as e:
        logger.error(f"Error running thread {thread_id}: {e}", exc_info=True)
        await activity_monitor.end_run(thread_id, "failed")


@celery_app.task(name="run_agent_task")
def run_agent_task(thread_id: str, inputs: Dict[str, Any]):
    """
    Celery Wrapper for Agent Execution.
    """
    logger.info(f"[Celery] Starting Agent Task for {thread_id}")
    
    # Event Loop Management
    loop = asyncio.get_event_loop()
    if loop.is_closed():
         loop = asyncio.new_event_loop()
         asyncio.set_event_loop(loop)
         
    loop.run_until_complete(_run_agent_logic(thread_id, inputs))
