
import asyncio
import logging
from typing import Dict, Any, List

# from celery import shared_task # Removed Celery
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

async def run_agent_background(thread_id: str, inputs: Dict[str, Any]):
    """
    Background Task Logic (FastAPI BackgroundTasks).
    Replaces Celery task. Runs in the main event loop, reusing global resources.
    """
    try:
        # 1. Deserialize
        if "messages" in inputs:
            deserialized_msgs = []
            for m in inputs["messages"]:
                if isinstance(m, dict):
                    if m.get("type") == "human":
                        deserialized_msgs.append(HumanMessage(content=m.get("content", "")))
                    else:
                        deserialized_msgs.append(m)
                else:
                    deserialized_msgs.append(m)
            inputs["messages"] = deserialized_msgs

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
        
        # Reinforce running state when background task starts
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

        # 3. Execution (Reuse Global Graph)
        try:
            callbacks = [callback, db_callback]
            callbacks.append(EvoLoopCallbackHandler(imagicbox_client, thread_id, command_id=evoloop_command_id))
                
            config["callbacks"] = callbacks
            config["recursion_limit"] = settings.RECURSION_LIMIT
            
            graph_instance = get_graph()
            if not graph_instance:
                raise ValueError("Global Graph not initialized")

            # Run Graph
            async for event in graph_instance.astream(inputs, config=config):
                # Check cancellation logic still applies via Redis
                await activity_monitor.check_cancellation(thread_id)
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
                
        except InterruptedError:
            logger.info(f"Task {thread_id} cancelled by user.")
            await activity_monitor.end_run(thread_id, "cancelled")
            
        except Exception as e:
            logger.error(f"Error running thread {thread_id}: {e}", exc_info=True)
            await activity_monitor.end_run(thread_id, "failed")
            
            # Persist Error
            try:
                from app.infrastructure.database.sql.models import Message
                async with session_scope() as session:
                    error_msg = Message(
                        thread_id=thread_id,
                        project_id=project_id,
                        role="ai", 
                        content=f"❌ **System Error**: Agent execution failed.\n\nError Details:\n> {str(e)}\n\nPlease try again or contact support.",
                        thinking=""
                    )
                    session.add(error_msg)
            except Exception as db_e:
                logger.error(f"Failed to persist error message: {db_e}")

    except Exception as outer_e:
        logger.critical(f"Fatal error in background dispatcher: {outer_e}")

