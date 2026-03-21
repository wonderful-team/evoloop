import logging
from typing import Any

from pydantic import BaseModel
from app.utils import render_template
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import BINARY_EXTENSIONS
from app.core.file.document_reader import document_reader_service
from app.models.conversation import Message

logger = logging.getLogger(__name__)


class ReferenceContext(BaseModel):
    content_blocks: list[dict[str, Any]]
    reference_notes: list[str]
    injected_message: str


class ReferenceService:
    """
    Service to handle the standardization and processing of message/file references.
    Converts raw attachments into LLM-ready context blocks and snippets.
    """

    async def process_references(
        self,
        message_text: str,
        attachments: list[dict[str, Any]],
        session: AsyncSession,
        project_id: int | None = None
    ) -> ReferenceContext:
        """
        Process a list of attachments and inject them into the communication context.
        """
        from app.core.evocloud import evocloud_manager

        content_blocks = []
        reference_notes = []
        updated_message = message_text

        # Get project root if project_id is provided (allow 0 for global mode)
        root_path = None
        if project_id is not None:
            project = await evocloud_manager.get_project_by_id(project_id)
            if project:
                root_path = project.get("path")

        quotes_data = []
        for att in attachments:
            att_type = att.get("type", "file")
            att_id = att.get("id") or att.get("url")
            att_name = att.get("name") or att_id or "Unknown"

            if not att_id:
                continue

            # 1. Message References
            if att_type == "message":
                snippet, note = await self._handle_message_reference(att_id, att_name, session)
                if snippet:
                    quotes_data.append({"type": "Message", "name": att_name, "content": snippet})
                if note:
                    reference_notes.append(note)

            # 2. File References
            elif att_type == "file":
                content, note = await self._handle_file_reference(att_id, att_name, root_path)
                if content:
                    quotes_data.append({"type": "File", "name": att_name, "content": content})
                if note:
                    reference_notes.append(note)

            # 3. Direct Image Attachments
            elif att_type == "image":
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": att_id}
                })
                reference_notes.append(f"Image Attachment: {att_name}")

            else:
                reference_notes.append(f"Attachment ({att_type}): {att_name}")
        
        # Render quotes using template
        if quotes_data:
            try:
                quoted_block = render_template("project/project_management.prompt.j2", quotes=quotes_data)
                updated_message = f"{message_text}\n\n{quoted_block}"
            except Exception as e:
                logger.error(f"Failed to render reference quotes: {e}")
                updated_message = message_text
        else:
            updated_message = message_text

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
            injected_message=updated_message
        )

    async def _handle_message_reference(self, msg_id_str: str, name: str, session: AsyncSession) -> tuple[str | None, str | None]:
        try:
            msg_id = int(msg_id_str)
            ref_msg = await session.get(Message, msg_id)
            if ref_msg and ref_msg.content:
                snippet = ref_msg.content[:500]
                if len(ref_msg.content) > 500:
                    snippet += "..."
                return snippet, f"Quoted Message: {name}"
        except (ValueError, TypeError):
            logger.warning(f"Invalid message reference ID: {msg_id_str}")
        except Exception as e:
            logger.error(f"Error fetching message reference {msg_id_str}: {e}")

        return None, f"Quoted Message (Fetch Failed): {name}"

    async def _handle_file_reference(self, file_path: str, name: str, root_path: str | None = None) -> tuple[str | None, str | None]:
        # Resolve path
        target_path = file_path
        if root_path and not os.path.isabs(file_path):
            target_path = os.path.join(root_path, file_path.lstrip("/"))

        # Binary check
        if any(target_path.lower().endswith(ext) for ext in BINARY_EXTENSIONS):
            logger.info(f"Skipping content injection for binary file: {target_path}")
            return None, f"Referencing Binary File (Content Skipped): {name}"

        try:
            content = await document_reader_service.read_document(target_path)
            snippet = content[:2000]
            if len(content) > 2000:
                snippet += "\n\n... (Content truncated for length)"
            return snippet, f"Referencing File: {name}"
        except Exception as e:
            logger.warning(f"Failed to read quoted file {target_path}: {e}")
            return None, f"Referencing File (Read Failed): {name}"


reference_service = ReferenceService()
