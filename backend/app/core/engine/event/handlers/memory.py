"""
Memory Command Handler
======================

Handles memory-related remote commands (add / update / delete) received
from the mobile gateway.
"""

import logging
import time
from typing import Any

from sqlalchemy import select

from app.constants import DEFAULT_PROJECT_ID
from app.core.evocloud.schemas import RemoteCommand
from app.infrastructure.database import session_scope
from app.models import Message
from app.utils.time import ts_from_dt

logger = logging.getLogger(__name__)


class MemoryCommandHandler:
    """
    Encapsulates memory add / update / delete command logic.

    Instantiated and dispatched to by ``EngineCommandSubscriber``.
    """

    async def handle(self, action: str, command: RemoteCommand) -> None:
        if action == "memory_add":
            await self._handle_memory_add(command)
        elif action == "memory_update":
            await self._handle_memory_update(command)
        elif action == "memory_delete":
            await self._handle_memory_delete(command)
        else:
            logger.debug(f"[MemoryCommand] Unknown action: {action}")

    async def _handle_memory_add(self, command: RemoteCommand) -> None:
        payload = command.get_payload()
        name = payload.get("name", "从对话学习")
        description = payload.get("description", "")
        project_id = self._resolve_project_id(payload, command)
        related_files = payload.get("related_files") or []
        source_message_id = payload.get("source_message_id")
        source_thread_id = payload.get("source_thread_id")
        created_by_member_id = payload.get("created_by_member_id")

        from app.core.memory.lifespan import MemoryLifespanManager

        manager = MemoryLifespanManager.get_manager()

        existing = None
        if source_message_id and created_by_member_id is not None:
            rows = await manager._storage._db_search({
                "source_message_id": source_message_id,
                "created_by_member_id": created_by_member_id,
                "memory_kind": "concept",
            })
            if rows:
                existing = await manager.get_memory(rows[0]["id"])

        if existing:
            await manager.delete_memory(existing.id)
            if source_message_id:
                await self._update_message_remember_state(
                    source_message_id, is_remembered=False, memory_concept_id=None
                )
            await self._sync_memory_to_gateway(project_id, [], deleted_names=[existing.title])
            logger.info(f"[EngineCommand] memory_add toggled off: name={existing.title}")
            return

        concept = await manager.store_concept(
            concept=name,
            description=description,
            project_id=project_id,
            related_files=related_files,
            member_id=created_by_member_id or 0,
            source_message_id=source_message_id,
            source_thread_id=source_thread_id,
            created_by_member_id=created_by_member_id,
            memory_kind="concept",
        )
        if source_message_id:
            await self._update_message_remember_state(
                source_message_id, is_remembered=True, memory_concept_id=concept.id
            )
        await self._sync_memory_to_gateway(project_id, [concept])
        logger.info(f"[EngineCommand] memory_add saved: name={name}")

    async def _update_message_remember_state(
        self,
        message_id: str,
        is_remembered: bool,
        memory_concept_id: str | None = None,
    ) -> None:
        from app.utils.time import utcnow

        async with session_scope() as session:
            stmt = select(Message).where(Message.id == message_id)
            res = await session.execute(stmt)
            msg = res.scalar_one_or_none()
            if not msg:
                logger.warning(f"[EngineCommand] Message not found for remember update: {message_id}")
                return
            msg.is_remembered = is_remembered
            msg.remembered_at = utcnow() if is_remembered else None
            msg.memory_concept_id = memory_concept_id if is_remembered else None

    async def _handle_memory_update(self, command: RemoteCommand) -> None:
        payload = command.get_payload()
        name = payload.get("name", "")
        description = payload.get("description")
        related_files = payload.get("related_files")
        project_id = self._resolve_project_id(payload, command)

        if not name:
            logger.warning("[EngineCommand] memory_update missing name, skipping")
            return

        logger.info(f"[EngineCommand] Processing memory_update: name={name}")
        from app.core.memory.lifespan import MemoryLifespanManager

        manager = MemoryLifespanManager.get_manager()
        memory_id = f"concept_{name.lower().replace(' ', '_')}"
        existing = await manager.get_memory(memory_id)
        if not existing:
            logger.warning(f"[EngineCommand] memory_update concept not found: {name}")
            return

        if description is not None:
            existing.content = description
            existing.description = description[:200]
        if related_files is not None:
            existing.tags = ["concept"] + related_files
        await manager.save_memory(existing)
        await self._sync_memory_to_gateway(project_id, [existing])
        logger.info(f"[EngineCommand] memory_update saved: name={name}")

    async def _handle_memory_delete(self, command: RemoteCommand) -> None:
        payload = command.get_payload()
        name = payload.get("name", "")
        source_message_id = payload.get("source_message_id")
        project_id = self._resolve_project_id(payload, command)

        if not name:
            logger.warning("[EngineCommand] memory_delete missing name, skipping")
            return

        logger.info(f"[EngineCommand] Processing memory_delete: name={name}")
        from app.core.memory.lifespan import MemoryLifespanManager

        manager = MemoryLifespanManager.get_manager()
        memory_id = f"concept_{name.lower().replace(' ', '_')}"
        existing = await manager.get_memory(memory_id)
        if existing:
            await manager.delete_memory(memory_id)

        if source_message_id:
            await self._update_message_remember_state(
                source_message_id, is_remembered=False, memory_concept_id=None
            )

        await self._sync_memory_to_gateway(project_id, [], deleted_names=[name])
        logger.info(f"[EngineCommand] memory_delete processed: name={name}")

    def _resolve_project_id(
        self, payload: dict[str, Any], command: RemoteCommand
    ) -> int:
        project_id = payload.get("project_id")
        if project_id is None:
            project_id = command.get("project_id")
        if project_id is None:
            project_id = DEFAULT_PROJECT_ID
        return project_id

    async def _sync_memory_to_gateway(
        self, project_id: int, memories: list, deleted_names: list[str] | None = None
    ) -> None:
        """Send memory.sync envelope to Gateway so Mobile can read from cloud."""
        try:
            from app.core.evocloud.manager import evocloud_manager

            link = evocloud_manager.link
            if not link or not link.is_connected():
                logger.debug("[EngineCommand] Gateway link not connected, skipping memory.sync")
                return

            concepts = []
            for m in memories:
                concept = {
                    "id": m.id,
                    "name": m.title,
                    "description": m.description,
                    "related_files": [t for t in (m.tags or []) if t != "concept"],
                    "project_id": project_id,
                    "source_message_id": m.source_message_id,
                    "source_thread_id": m.source_thread_id,
                    "deleted": False,
                    "created_at": ts_from_dt(m.created_at),
                    "updated_at": ts_from_dt(m.updated_at),
                }
                if not concept["name"]:
                    concept["name"] = m.content[:20]
                concepts.append(concept)

            if deleted_names:
                for name in deleted_names:
                    concepts.append({
                        "id": f"concept_{name.lower().replace(' ', '_')}",
                        "name": name,
                        "description": "",
                        "related_files": [],
                        "project_id": project_id,
                        "deleted": True,
                        "created_at": 0,
                        "updated_at": int(time.time()),
                    })

            body = {
                "project_id": project_id,
                "concepts": concepts,
            }
            from app.core.channel import channel_registry
            ch = channel_registry.get("mobile")
            if ch:
                await ch.send_envelope(
                    env_type="memory.sync",
                    body=body,
                    member_id=0,
                )
            logger.info(f"[EngineCommand] memory.sync sent to Gateway: concepts={len(concepts)}")
        except Exception as e:
            logger.error(f"[EngineCommand] Failed to send memory.sync: {e}")
