import asyncio
import logging

from app.core.context import thread_context_store
from app.core.engine.background_agent import run_agent_background
from app.core.evocloud import evocloud_manager
from app.core.evocloud.schemas import RemoteCommand, ProjectSwitchEvent

logger = logging.getLogger(__name__)


async def handle_remote_command(command: RemoteCommand):
    """
    Common handler for remote commands from EvoLoop Cloud.
    Can be used by both login.py (auto-connect) and main.py (startup recovery).
    """
    cmd_type = command.get("type", "chat_message")

    # [HITL Inbound Logic]
    if cmd_type == "hitl_response":
        thread_id = command.get("thread_id")
        response = (command.get("content") or {}).get("response")

        if thread_id and response is not None:
            logger.info(f"[EvoLoop] Processing HITL Response for thread {thread_id}: {response}")

            from app.core.engine.background_agent import BackgroundAgentInputs
            inputs = BackgroundAgentInputs(
                hitl_resume_response=response,
                command_id=command.get("command_id")
            )
            asyncio.create_task(run_agent_background(thread_id, inputs))
        return

    # Support both nested 'content' (legacy/cloud) and flat 'message' (mobile/local) structures
    content_obj = command.get("content", {})
    params_obj = content_obj.get("params", {})

    message = (
        command.get("message") or
        content_obj.get("text") or
        content_obj.get("message") or
        params_obj.get("message")
    )

    attachments = (
        command.get("attachments") or
        content_obj.get("attachments") or
        params_obj.get("attachments") or
        []
    )

    if message or attachments:
        thread_id = command.get("thread_id") or "remote-default"
        logger.info(f"[EvoLoop] Executing remote command on thread {thread_id}: Length={len(message) if message else 0}, Attachments={len(attachments)}")

        # Resolve Project ID:
        pid_from_payload = command.get("project_id")
        pid_from_context = thread_context_store.get_active_project("remote-default")

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

        from app.core.engine.background_agent import BackgroundAgentInputs
        inputs = BackgroundAgentInputs(
            messages=messages,
            project_id=project_id,
            command_id=command.get("command_id"),
        )

        # Log User Message to Detailed Logs (For Tool/Thought View consistency)
        asyncio.create_task(
            evocloud_manager.upload_log(
                thread_id=thread_id,
                log_type="user",
                content=message or "[Attachment]",
                project_id=project_id,
                command_id=command.get("command_id")
            )
        )

        # Run agent in background (Local)
        asyncio.create_task(run_agent_background(thread_id, inputs))


async def handle_project_switch_event(event_type: str, event: ProjectSwitchEvent):
    """
    Handle project switch event from Cloud.
    """
    project_id = event.project_id
    project_name = event.project_name

    path = event.external_path
    if not path:
        # Fallback: maybe it's passed as 'path'
        path = event.path

    if path:
        logger.info(f"[EvoLoop] Received Switch Project Event: {project_id} ({project_name}) -> {path}")

        # 1. Update Context (Global / Thread agnostic)
        thread_context_store.set_working_directory("remote-default", path)
        thread_context_store.set_working_directory("default", path)

        if project_id:
            thread_context_store.set_active_project("remote-default", project_id)
            thread_context_store.set_active_project("default", project_id)

        # 2. Emit project.switched event instead of directly starting indexing
        from app.core.events.base import BaseEvent, system_bus
        await system_bus.publish(BaseEvent(
            event_type="project.switched",
            source="evocloud_bridge",
            data={"project_id": project_id, "path": path}
        ))
        logger.info(f"[EvoLoop] Emitted project.switched event for {path}")

    else:
        logger.warning(f"[EvoLoop] Switch Project Event received but no path provided: {event.model_dump()}")
