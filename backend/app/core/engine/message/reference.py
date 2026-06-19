import logging
import os
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import BINARY_EXTENSIONS, DEFAULT_PROJECT_ID
from app.core.engine.message.schemas import ReferenceContext
from app.core.file.document_reader import document_reader_service
from app.models.conversation import Message
from app.utils import render_template

logger = logging.getLogger(__name__)


class ReferenceService:
    """
    Service to handle the standardization and processing of message/file references.
    Converts raw references into LLM-ready context blocks and snippets.
    """

    async def process_references(
        self,
        message_text: str,
        references_input: list[dict[str, Any]],
        session: AsyncSession,
        root_path: str | None = None,
        project_id: int = DEFAULT_PROJECT_ID
    ) -> ReferenceContext:
        """
        Process a list of references and inject them into the communication context.
        接收 root_path 进行解耦，不再内部依赖 evocloud_manager 获取项目路径。
        """
        content_blocks = []
        reference_notes = []
        references = []

        quotes_data = []
        for att in references_input:
            att_type = att.get("type", "file")
            att_id = att.get("target_id") or att.get("id") or att.get("url")
            att_name = att.get("target_name") or att.get("name") or att_id or "Unknown"

            if not att_id:
                continue

            # 1. Message References
            if att_type == "message":
                snippet, note = await self._handle_message_reference(att_id, att_name, session)
                if snippet:
                    quotes_data.append({"type": "Message", "name": att_name, "content": snippet})
                if note:
                    reference_notes.append(note)

                # 为数据库持久化记录引用
                references.append({
                    "id": str(uuid.uuid4()),
                    "type": "message",
                    "target_id": att_id,
                    "target_name": att_name,
                    "metadata": {"snippet": snippet}
                })

            # 2. File References
            elif att_type == "file":
                content, note = await self._handle_file_reference(att_id, att_name, root_path)
                if content:
                    quotes_data.append({"type": "File", "name": att_name, "content": content})
                if note:
                    reference_notes.append(note)

                # 保留原始 source_path，target_id 保持为可直接访问的 raw URL
                source_path = att.get("source_path") or att.get("metadata", {}).get("source_path") or att_id
                if source_path.startswith(("http", "/api/", "file://")):
                    target_id = source_path
                else:
                    target_id = f"/api/v1/files/raw?project_id={project_id}&path={source_path}"

                # 为数据库持久化记录引用
                references.append({
                    "id": str(uuid.uuid4()),
                    "type": "file",
                    "target_id": target_id,
                    "target_name": att_name,
                    "metadata": {
                        "filename": att_name,
                        "source_path": source_path,
                    },
                })

            # 3. Direct Image References
            elif att_type == "image":
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": att_id}
                })
                reference_notes.append(f"Image Reference: {att_name} (Path: {att_id})")
                references.append({
                    "id": str(uuid.uuid4()),
                    "type": "image",
                    "target_id": att_id,
                    "target_name": att_name,
                    "metadata": {"filename": att_name}
                })

            # 4. Audio References
            elif att_type == "audio":
                content_blocks.append({
                    "type": "text",
                    "text": f"[Audio: {att_name}]({att_id})"
                })
                reference_notes.append(f"Audio Reference: {att_name} (Path: {att_id})")
                references.append({
                    "id": str(uuid.uuid4()),
                    "type": "audio",
                    "target_id": att_id,
                    "target_name": att_name,
                    "metadata": {"filename": att_name},
                })

            # 5. Skill References
            elif att_type == "skill":
                metadata = att.get("metadata") or att.get("meta_data") or {}
                skill_id = metadata.get("skill_id") or att_id
                skill_name = metadata.get("skill_name") or att_name
                skill_description = metadata.get("description", "")
                reference_notes.append(f"Skill: {skill_name} (ID: {skill_id})")
                quotes_data.append({
                    "type": "Skill",
                    "name": skill_name,
                    "content": f"Using learned skill: {skill_name}"
                })
                references.append({
                    "id": str(uuid.uuid4()),
                    "type": "skill",
                    "target_id": skill_id,
                    "target_name": skill_name,
                    "metadata": {
                        "skill_id": skill_id,
                        "skill_name": skill_name,
                        "description": skill_description,
                    },
                })

            else:
                reference_notes.append(f"Reference ({att_type}): {att_name}")

        # Render quotes using template
        updated_message = message_text
        if quotes_data:
            # 模板路径保持不变，或者后续根据需要迁移模板
            quoted_block = render_template("domain/project/project_management.prompt.j2", quotes=quotes_data)
            updated_message = f"{message_text}\n\n{quoted_block}"

        # Final assembly of the text block
        final_text = updated_message
        if reference_notes:
            notes_section = "\n\n" + "\n".join([f"[{note}]" for note in reference_notes])
            final_text += notes_section

        content_blocks.insert(0, {
            "type": "text",
            "text": final_text
        })

        return ReferenceContext(
            content_blocks=content_blocks,
            reference_notes=reference_notes,
            injected_message=updated_message,
            references=references
        )

    async def _handle_message_reference(self, msg_id_str: str, name: str, session: AsyncSession) -> tuple[str | None, str | None]:
        try:
            ref_msg = await session.get(Message, msg_id_str)
            if ref_msg and ref_msg.content:
                snippet = ref_msg.content[:500]
                if len(ref_msg.content) > 500:
                    snippet += "..."
                return snippet, f"Quoted Message: {name}"
        except Exception as e:
            logger.error(f"Error fetching message reference {msg_id_str}: {e}")

        return None, f"Quoted Message (Fetch Failed): {name}"

    async def _handle_file_reference(self, file_path: str, name: str, root_path: str | None = None) -> tuple[str | None, str | None]:
        target_path = self._resolve_local_path(file_path, root_path)

        if any(target_path.lower().endswith(ext) for ext in BINARY_EXTENSIONS):
            logger.info(f"Skipping content injection for binary file: {target_path}")
            return None, f"Referencing Binary File (Content Skipped): {name}"

        try:
            content = await document_reader_service.read_document(target_path)
            snippet = content[:2000]
            if len(content) > 2000:
                snippet += "\n\n... (Content truncated for length)"
            return snippet, f"Referencing File: {name} (Path: {file_path})"
        except Exception as e:
            logger.warning(f"Failed to read quoted file {target_path}: {e}")
            return None, f"Referencing File (Read Failed): {name} (Path: {file_path})"

    def _resolve_local_path(self, file_path: str, root_path: str | None) -> str:
        # 1. API URL: /api/v1/files/raw?path=uploads/xxx → extract path param, resolve locally
        if file_path.startswith("/api/"):
            parsed = urlparse(file_path)
            params = parse_qs(parsed.query)
            inner_path = params.get("path", [None])[0]
            if inner_path:
                return self._resolve_upload_path(inner_path, root_path)
            return file_path

        # 2. file:// URL: strip scheme, use absolute path directly
        if file_path.startswith("file://"):
            return file_path[len("file://"):]

        # 3. http/https URL: cannot read locally, return as-is (caller handles failure)
        if file_path.lower().startswith(("http://", "https://")):
            return file_path

        # 4. Local path: resolve uploads/ prefix, join with root_path if provided
        if not os.path.isabs(file_path):
            return self._resolve_upload_path(file_path, root_path)

        return file_path

    @staticmethod
    def _resolve_upload_path(path: str, root_path: str | None) -> str:
        rel_path = path
        if rel_path.startswith("uploads/"):
            rel_path = rel_path[len("uploads/"):]
        if root_path:
            return os.path.join(root_path, rel_path.lstrip("/"))
        return rel_path


reference_service = ReferenceService()
