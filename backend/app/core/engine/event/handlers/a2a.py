"""
A2A Command Handler
===================

Handles Agent-to-Agent (A2A) task and callback commands received
from the mobile gateway or peer agents.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.evocloud.manager import evocloud_manager
from app.core.evocloud.schemas import AgentTask, AgentTaskResult, RemoteCommand
from app.infrastructure.config import SystemConfigService
from app.infrastructure.database import session_scope
from app.models import Conversation, Message
from app.utils.template import render_template

logger = logging.getLogger(__name__)


class A2ACommandHandler:
    """
    Encapsulates A2A task / callback command logic.

    Instantiated and dispatched to by ``EngineCommandSubscriber``.
    """

    async def handle(self, action: str, command: RemoteCommand) -> None:
        if action == "a2a_task":
            await self._handle_a2a_task(command)
        elif action == "a2a_callback":
            await self._handle_a2a_callback(command)
        else:
            logger.debug(f"[A2A] Unknown action: {action}")

    async def _handle_a2a_task(self, command: RemoteCommand) -> None:
        payload = command.get_payload()
        logger.info(f"[A2A] Received A2A Task: {payload}")

        try:
            task = AgentTask.model_validate(payload)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[A2A] Invalid AgentTask payload: {payload}, error={e}")
            return

        thread_id = task.task_id

        # Loop prevention check
        if task.hop_count > task.max_hops:
            logger.error(
                f"[A2A] Maximum hops exceeded: {task.hop_count} > {task.max_hops} for task {task.task_id}"
            )
            await self._send_a2a_error(task, "Maximum chain delegation depth exceeded")
            return

        # Download attachments
        local_attachment_paths = []
        if task.attachments:
            download_dir = os.path.expanduser(
                os.path.join(settings.EVOLOOP_APP_DATA_DIR, "attachments", task.task_id)
            )
            os.makedirs(download_dir, exist_ok=True)

            async with httpx.AsyncClient() as client:
                for att in task.attachments:
                    dest_path = os.path.join(download_dir, att.filename)
                    logger.info(
                        f"[A2A] Downloading attachment {att.filename} from {att.download_url}..."
                    )
                    try:
                        async with client.stream("GET", att.download_url) as response:
                            response.raise_for_status()
                            with open(dest_path, "wb") as f:
                                async for chunk in response.aiter_bytes():
                                    f.write(chunk)

                        # Verify MD5
                        import hashlib

                        hash_md5 = hashlib.md5()
                        with open(dest_path, "rb") as f:
                            for chunk in iter(lambda: f.read(4096), b""):
                                hash_md5.update(chunk)
                        actual_md5 = hash_md5.hexdigest()

                        if actual_md5 != att.md5:
                            logger.error(
                                f"[A2A] MD5 mismatch for {att.filename}. Expected: {att.md5}, Got: {actual_md5}"
                            )
                            await self._send_a2a_error(
                                task, f"Attachment MD5 mismatch for {att.filename}"
                            )
                            return

                        local_attachment_paths.append(dest_path)
                    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as ex:
                        logger.error(
                            f"[A2A] Failed to download/verify attachment {att.filename}: {ex}"
                        )
                        await self._send_a2a_error(
                            task, f"Failed to download attachment {att.filename}: {ex}"
                        )
                        return

        executor_device_key = (
            evocloud_manager.link.device_key
            if evocloud_manager.link
            else "unknown-worker"
        )
        executor_device_name = settings.EVOCLOUD_DEVICE_NAME

        project_id = command.get("project_id") or DEFAULT_PROJECT_ID

        async with session_scope() as session:
            conv = await session.get(Conversation, thread_id)
            if not conv:
                conv = Conversation(
                    id=thread_id,
                    project_id=project_id,
                    title=f"A2A: {task.instruction[:30]}",
                    root_thread_id=task.root_thread_id,
                    parent_thread_id=task.parent_thread_id,
                    caller_device_key=task.caller_device_key,
                    executor_device_key=executor_device_key,
                    executor_device_name=executor_device_name,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(conv)

        # Inject System Prompt Context
        system_content = render_template(
            "core/engine/a2a_system.prompt.j2",
            caller_device_key=task.caller_device_key,
            caller_role=task.caller_role,
            global_goal=task.global_goal,
            instruction=task.instruction,
            local_attachment_paths=local_attachment_paths,
        )

        from app.core.engine.message.repository import MessageRepository

        repo = MessageRepository(thread_id, project_id=project_id)
        await repo.persist(
            role="system",
            content=system_content,
            category="internal_system",
            is_visible=True,
        )

        # Dispatch Agent Run
        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=task.instruction,
            project_id=project_id,
            command_id=command.get("command_id"),
            model=None,
            metadata={
                "task_type": "a2a_task",
                "task_id": task.task_id,
                "caller_device_key": task.caller_device_key,
                "root_thread_id": task.root_thread_id,
                "parent_thread_id": task.parent_thread_id,
            },
        )

        if result.status == "failed":
            logger.error(f"[A2A] Dispatch failed for A2A task: {result.error}")
            await self._send_a2a_error(task, f"Agent dispatch failed: {result.error}")
            return

        asyncio.create_task(run_agent_background(thread_id, result.inputs))

    async def _send_a2a_error(self, task: Any, error_msg: str) -> None:
        from app.core.evocloud.manager import evocloud_manager

        callback_payload = AgentTaskResult(
            task_id=task.task_id,
            status="failed",
            error=error_msg,
            summary=f"Error: {error_msg}",
        )

        cmd_data = {
            "action": "a2a_callback",
            "content": callback_payload.model_dump(),
            "thread_id": task.parent_thread_id,
        }

        try:
            await evocloud_manager.api.send_command_to_device(
                device_key=task.caller_device_key, cmd_data=cmd_data
            )
            logger.info(
                f"[A2A] Error callback sent to caller {task.caller_device_key} for task {task.task_id}"
            )
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(
                f"[A2A] Failed to send error callback to caller {task.caller_device_key}: {e}"
            )

    async def _handle_a2a_callback(self, command: RemoteCommand) -> None:
        payload = command.get_payload()
        logger.info(f"[A2A] Received A2A Callback: {payload}")

        try:
            result = AgentTaskResult.model_validate(payload)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[A2A] Invalid AgentTaskResult: {payload}, error={e}")
            return

        task_id = result.task_id
        caller_thread_id = command.get("thread_id")

        if not caller_thread_id:
            from app.infrastructure.database import session_scope
            from app.models import Conversation

            async with session_scope() as session:
                conv = await session.get(Conversation, task_id)
                if conv:
                    caller_thread_id = conv.parent_thread_id

        if not caller_thread_id:
            logger.error(f"[A2A] Caller thread_id not found for task_id: {task_id}")
            return

        # Clear human request on Caller thread
        from app.core.monitoring.activity import activity_monitor

        await activity_monitor.clear_human_request(caller_thread_id)

        # Build response payload
        result_content = json.dumps(result.model_dump(), ensure_ascii=False)

        # Close the pending tool call message
        tool_call_id = None
        from app.infrastructure.database import session_scope

        async with session_scope() as session:
            stmt = (
                select(Message)
                .where(Message.thread_id == caller_thread_id)
                .where(Message.role == "ai")
                .order_by(Message.sequence_number.desc())
                .limit(5)
            )
            res = await session.execute(stmt)
            messages = res.scalars().all()
            for msg in messages:
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        if tc.get("name") in ("SendAgentTaskTool", "send_agent_task"):
                            tool_call_id = tc.get("id")
                            break
                if tool_call_id:
                    break

        if tool_call_id:
            from app.core.hitl.orchestrator import close_hitl_interaction

            await close_hitl_interaction(caller_thread_id, tool_call_id, "completed")
        else:
            logger.warning(
                f"[A2A] Could not find matching pending tool call for task_id {task_id}"
            )

        # Resume Caller Agent
        from app.core.context.manager import ContextManager
        from app.core.engine.background_agent import BackgroundAgentInputs

        loaded_ctx = await ContextManager.load(caller_thread_id)
        model = loaded_ctx.active_model if loaded_ctx else None
        if not model:
            model = SystemConfigService.get_value("LLM_MODEL")
        if not model:
            # Fallback: 从 Gateway 拉取第一个可用的平台 LLM 模型
            # 适用于进程重启后 ContextManager 丢失、且本地 DB 未配置 LLM_MODEL 的情况
            try:
                from app.infrastructure.llm.platform_service import llm_platform_service

                platform_models = await llm_platform_service.fetch_platform_models()
                llm_models = [m for m in platform_models if m.model_type == "llm"]
                if llm_models:
                    model = llm_models[0].model_id
                    logger.info(f"[A2A] Model resolved from platform: {model}")
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(
                    f"[A2A] Failed to fetch platform models for fallback: {e}"
                )

        if not model:
            logger.error(
                f"[A2A] Cannot resume Caller thread {caller_thread_id}: no model available"
            )
            return

        inputs = BackgroundAgentInputs(
            hitl_resume_response=result_content,
            model=model,
        )
        logger.info(f"[A2A] Resuming Caller Agent on thread {caller_thread_id}")
        asyncio.create_task(run_agent_background(caller_thread_id, inputs))
