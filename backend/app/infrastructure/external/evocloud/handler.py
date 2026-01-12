
from app.logging import logger


async def handle_remote_command(command_data: dict):
    """
    Common handler for remote commands from EvoLoop Cloud.
    Can be used by both login.py (auto-connect) and main.py (startup recovery).
    """
    # agent.py imports get_evoloop_client which is in client.py
    # client.py imports nothing, but main.py sets up everything.
    # If handler is imported at top level in main, it's fine.
    # But if handler depends on agent, and agent depends on client (which might use handler type hint), it can be tricky.
    # The error "No module named 'core'" suggests a deeper issue or misconfiguration in execution context,
    # but based on the code structure, agent.py <-> infrastructure/evoloop_link is a likely cycle.
    # from app.api.routes.agent import run_agent_background

    # Support both nested 'content' (legacy/cloud) and flat 'message' (mobile/local) structures
    content_obj = command_data.get("content", {})
    message = command_data.get("message") or content_obj.get("text") or content_obj.get("message")
    attachments = command_data.get("attachments") or content_obj.get("attachments") or []

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
                # Note: File/Other attachments might need different handling or explicit text mention?
                # For now handled as image or ignored if not visual.
                # If file, we might append a link to text block?
                elif att.get("type") == "file":
                    # Append file link to text if not already there?
                    # Or just add a text block?
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
            "command_id": command_data.get("command_id")
        }

        # Run agent in background (Local)
        import asyncio

        from app.core.engine.tasks import run_agent_background
        asyncio.create_task(run_agent_background(thread_id, inputs))


async def handle_project_switch_event(event_data: dict):
    """
    Handle project switch event from Cloud.
    Payload (event_data) structure:
    {
        "project_id": 1,
        "project_name": "...",
        "external_path": "/path/to/project", // If available
        ...
    }
    """
    from app.domain.project.service import project_context_manager
    # Circular dependency risk with agent.py depending on how it's imported.
    # But this handler is imported by main/client.

    project_id = event_data.get("project_id")
    project_name = event_data.get("project_name")

    # Check if we have a path.
    # Cloud should send 'external_path' if it knows the local path (sync mode).
    # Or we might need to look it up locally if we have a mapping.
    # For now, assume cloud sends 'external_path' which corresponds to local path
    # OR we use project_id to find it if we have a local lookup.

    # Logic:
    # 1. Prefer external_path from payload.
    # 2. If not, try to find by ID in local DB? (Not implemented fully yet)

    path = event_data.get("external_path")

    if not path:
        # Fallback: maybe it's passed as 'path'
        path = event_data.get("path")

    if path:
        logger.info(f"[EvoLoop] Received Switch Project Event: {project_id} ({project_name}) -> {path}")

        # 1. Update Context (Global / Thread agnostic)
        # Note: set_working_directory sets it for a specific thread.
        # But here we want to switch the "Global Active Project" or "The Device's Current Focus".
        # If the device is single-user single-focus, we might want to update a default context.
        # Let's update "default" thread context, and maybe "remote-default".

        project_context_manager.set_working_directory("remote-default", path)
        project_context_manager.set_working_directory("default", path)

        if project_id:
            project_context_manager.set_active_project("remote-default", project_id)
            project_context_manager.set_active_project("default", project_id)

        # 2. Start Indexing/Watching if not already
        import os

        from app.domain.codebase.indexing.manager import indexing_manager
        from app.domain.codebase.indexing.service import IndexingService

        try:
            service = IndexingService()
            repo_name = os.path.basename(path)
            repo = await service.get_or_create_repo(path, repo_name, project_id=project_id)
            await indexing_manager.start_watching(path, repo.id)
            logger.info(f"[EvoLoop] Started watching {path}")

            # NEW: Trigger Smart Full-Indexing for "Staleness Check"
            # Since index_repository is incremental (MD5 check), this is cheap.
            indexing_manager.run_indexing_background(repo.id)

        except Exception as e:
            logger.error(f"[EvoLoop] Failed to start watching {path}: {e}")

    else:
        logger.warning(f"[EvoLoop] Switch Project Event received but no path provided: {event_data}")
