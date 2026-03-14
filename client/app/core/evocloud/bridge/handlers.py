import asyncio
import logging

from app.core.context import thread_context_store
from app.core.evocloud import evocloud_manager

logger = logging.getLogger(__name__)


async def handle_remote_command(command_data: dict):
    """
    Handle remote commands from EvoLoop Cloud.

    In Sidecar architecture, Client does NOT run Agent locally.
    Commands are forwarded to Tauri (center) which coordinates with Server (cloud).
    """
    cmd_type = command_data.get("type", "chat_message")
    thread_id = command_data.get("thread_id", "remote-default")

    # Log the command for debugging
    logger.info(f"[EvoLoop] Received remote command: {cmd_type} on thread {thread_id}")

    # Forward to Tauri via events system (events are handled by sidecar protocol)
    from app.sidecar.handlers.events import events

    if cmd_type == "hitl_response":
        await events.hitl_response(
            thread_id=thread_id,
            response=command_data.get("content", {}).get("response"),
            command_id=command_data.get("command_id")
        )
    elif cmd_type == "chat_message":
        content_obj = command_data.get("content", {})
        message = (
            command_data.get("message") or
            content_obj.get("text") or
            content_obj.get("message")
        )
        attachments = (
            command_data.get("attachments") or
            content_obj.get("attachments") or
            []
        )

        await events.chat_message(
            thread_id=thread_id,
            message=message,
            attachments=attachments,
            project_id=command_data.get("project_id"),
            command_id=command_data.get("command_id")
        )
    else:
        # Generic command forwarding
        await events.remote_command(
            command_type=cmd_type,
            data=command_data
        )


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
        thread_context_store.set_working_directory("remote-default", path)
        thread_context_store.set_working_directory("default", path)

        if project_id:
            thread_context_store.set_active_project("remote-default", project_id)
            thread_context_store.set_active_project("default", project_id)

        # 2. Emit project.switched event instead of directly starting indexing
        from app.core.events.base import BaseEvent, system_bus
        event = BaseEvent(
            event_type="project.switched",
            source="evocloud_bridge",
            data={"project_id": project_id, "path": path}
        )
        await system_bus.publish(event)
        logger.info(f"[EvoLoop] Emitted project.switched event for {path}")

    else:
        logger.warning(f"[EvoLoop] Switch Project Event received but no path provided: {event_data}")
