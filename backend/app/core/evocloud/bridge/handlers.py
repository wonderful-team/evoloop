import asyncio
import logging
import uuid

from app.core.context import thread_context_store
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.evocloud.schemas import ProjectSwitchEvent, RemoteCommand

logger = logging.getLogger(__name__)


async def handle_remote_command(command: RemoteCommand):
    """
    Common handler for remote commands from EvoLoop Cloud.

    chat_message:
        Delegates to dispatch_agent_run() so that WebSocket and HTTP /chat
        share the same persistence, reference processing, and model fallback.

    hitl_response:
        Directly resumes the agent with the human-provided answer.
    """
    cmd_type = command.get("type", "chat_message")

    # [HITL Inbound Logic]
    if cmd_type == "hitl_response":
        thread_id = command.get("thread_id")
        response = (command.get("content") or {}).get("response")

        if thread_id and response is not None:
            logger.info(f"[EvoLoop] Processing HITL Response for thread {thread_id}")

            # Persist the response message so it appears in history
            from app.core.engine.dispatch import persist_user_message
            await persist_user_message(
                thread_id=thread_id,
                content=str(response),
                project_id=command.get("project_id"),
                command_id=command.get("command_id"),
            )

            from app.core.engine.background_agent import BackgroundAgentInputs
            from app.core.context.manager import ContextManager

            # Resolve model: prefer existing session model, fallback to system default
            loaded_ctx = await ContextManager.load(thread_id)
            model = loaded_ctx.active_model if loaded_ctx else None
            if not model:
                from app.infrastructure.config.service import SystemConfigService
                model = SystemConfigService.get_value("LLM_MODEL")

            inputs = BackgroundAgentInputs(
                hitl_resume_response=response,
                command_id=command.get("command_id"),
                model=model,
            )
            asyncio.create_task(run_agent_background(thread_id, inputs))
        return

    # Support both nested 'content' (legacy/cloud) and flat 'message' (mobile/local) structures
    content_obj = command.get("content") or {}
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

    if not message and not attachments:
        logger.debug("[EvoLoop] Remote command has no message or attachments, skipping")
        return

    thread_id = command.get("thread_id")
    if not thread_id:
        logger.error("[EvoLoop] Remote command missing thread_id, rejecting")
        raise ValueError("thread_id is required in remote command")
    logger.info(
        f"[EvoLoop] Executing remote command on thread {thread_id}: "
        f"Length={len(message) if message else 0}, Attachments={len(attachments)}"
    )

    # Resolve Project ID
    pid_from_payload = command.get("project_id")
    pid_from_context = thread_context_store.get_active_project("remote-default")
    project_id = pid_from_payload or pid_from_context or 1

    # Unified dispatch preparation (DB persistence, EvoCloud sync, model fallback)
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message or "",
        project_id=project_id,
        attachments=attachments,
        command_id=command.get("command_id"),
        model=None,  # Remote commands don't carry model selection; fallback to default
    )

    if result.status == "failed":
        logger.error(f"[EvoLoop] Dispatch failed for remote command: {result.error}")
        raise RuntimeError(f"Agent dispatch failed: {result.error}")

    # Start agent in background
    asyncio.create_task(run_agent_background(thread_id, result.inputs))


async def handle_project_switch_event(_event_type: str, event: ProjectSwitchEvent):
    """
    Handle project switch event from Cloud.
    """
    project_id = event.project_id
    project_name = event.project_name

    path = event.external_path
    if not path:
        path = event.path

    if path:
        logger.info(f"[EvoLoop] Received Switch Project Event: {project_id} ({project_name}) -> {path}")

        thread_context_store.set_working_directory("remote-default", path)
        thread_context_store.set_working_directory("default", path)

        if project_id:
            thread_context_store.set_active_project("remote-default", project_id)
            thread_context_store.set_active_project("default", project_id)

        from app.core.events.base import BaseEvent, system_bus
        await system_bus.publish(BaseEvent(
            event_type="project.switched",
            source="evocloud_bridge",
            data={"project_id": project_id, "path": path}
        ))
        logger.info(f"[EvoLoop] Emitted project.switched event for {path}")

    else:
        logger.warning(f"[EvoLoop] Switch Project Event received but no path provided: {event.model_dump()}")
