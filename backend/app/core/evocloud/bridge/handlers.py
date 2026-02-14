import asyncio
import logging
import os

from app.core.engine.background_agent import run_agent_background
from app.core.evocloud import evocloud_manager
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.codebase.indexing.service import IndexingService
from app.domain.project.service import project_context_manager

logger = logging.getLogger(__name__)


async def handle_remote_command(command_data: dict):
    """
    Common handler for remote commands from EvoLoop Cloud.
    Can be used by both login.py (auto-connect) and main.py (startup recovery).
    """
    cmd_type = command_data.get("type", "chat_message")

    # [HITL Inbound Logic]
    if cmd_type == "hitl_response":
        thread_id = command_data.get("thread_id")
        response = command_data.get("content", {}).get("response")

        if thread_id and response is not None:
             logger.info(f"[EvoLoop] Processing HITL Response for thread {thread_id}: {response}")

             inputs = {
                 "hitl_resume_response": response,
                 "command_id": command_data.get("command_id")
             }
             asyncio.create_task(run_agent_background(thread_id, inputs))
        return

    # Support both nested 'content' (legacy/cloud) and flat 'message' (mobile/local) structures
    content_obj = command_data.get("content", {})
    params_obj = content_obj.get("params", {})

    message = (
        command_data.get("message") or 
        content_obj.get("text") or 
        content_obj.get("message") or
        params_obj.get("message")
    )

    attachments = (
        command_data.get("attachments") or 
        content_obj.get("attachments") or 
        params_obj.get("attachments") or
        []
    )

    if message or attachments:
        thread_id = command_data.get("thread_id") or "remote-default"
        logger.info(f"[EvoLoop] Executing remote command on thread {thread_id}: Length={len(message) if message else 0}, Attachments={len(attachments)}")

        # Resolve Project ID:
        from app.domain.project.service import project_context_manager

        pid_from_payload = command_data.get("project_id")
        pid_from_context = project_context_manager.get_active_project("remote-default")

        project_id = pid_from_payload or pid_from_context or 1

        # Construct input state
        if attachments:
            # Construct Multimodal Message (List of Content Blocks)
            # Frontend sends: { type: 'image', url: '...' } or { type: 'file', url: '...' }
            # Agent Engine Expects: { type: 'text', text: '...' } or { type: 'image_url', image_url: { url: '...' } }

            content_blocks = []
            if message:
                content_blocks.append({"type": "text", "text": message})

            for att in attachments:
                if att.get("type") == "image":
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": att.get("url")}
                    })
                elif att.get("type") == "file":
                    content_blocks.append({
                        "type": "text",
                        "text": f"\n[File: {att.get('url')}]"
                    })

            messages = [{"type": "human", "content": content_blocks}]
        else:
            messages = [{"type": "human", "content": message}]

        inputs = {
            "messages": messages,
            "project_id": project_id,
            "command_id": command_data.get("command_id"),
        }

        # Log User Message to Detailed Logs (For Tool/Thought View consistency)
        asyncio.create_task(
            evocloud_manager.upload_log(
                thread_id=thread_id,
                log_type="user",
                content=message or "[Attachment]",
                project_id=project_id,
                command_id=command_data.get("command_id")
            )
        )

        # Run agent in background (Local)
        asyncio.create_task(run_agent_background(thread_id, inputs))


async def handle_project_switch_event(event_data: dict):
    """
    Handle project switch event from Cloud.
    """
    project_id = event_data.get("project_id")
    project_name = event_data.get("project_name")

    path = event_data.get("external_path")
    if not path:
        # Fallback: maybe it's passed as 'path'
        path = event_data.get("path")

    if path:
        logger.info(f"[EvoLoop] Received Switch Project Event: {project_id} ({project_name}) -> {path}")

        # 1. Update Context (Global / Thread agnostic)
        project_context_manager.set_working_directory("remote-default", path)
        project_context_manager.set_working_directory("default", path)

        if project_id:
            project_context_manager.set_active_project("remote-default", project_id)
            project_context_manager.set_active_project("default", project_id)

        # 2. Start Indexing/Watching if not already
        try:
            service = IndexingService()
            repo_name = os.path.basename(path)
            repo = await service.get_or_create_repo(path, repo_name, project_id=project_id)
            await indexing_manager.start_watching(path, repo.id)
            logger.info(f"[EvoLoop] Started watching {path}")

            # NEW: Trigger Smart Full-Indexing for "Staleness Check"
            indexing_manager.run_indexing_background(repo.id)

        except Exception as e:
            logger.error(f"[EvoLoop] Failed to start watching {path}: {e}")

    else:
        logger.warning(f"[EvoLoop] Switch Project Event received but no path provided: {event_data}")
