import logging
import os

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.factory import LLMFactory
from app.i18n.service import i18n
from app.infrastructure.database.sql.models import CodeEntity, SourceFile

logger = logging.getLogger(__name__)


class WikiService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_doc_for_entity(self, entity_id: int) -> str:
        """
        Generate markdown documentation for a specific entity.
        """
        # 1. Fetch Entity & Source Code
        stmt = (
            select(CodeEntity, SourceFile)
            .join(SourceFile, CodeEntity.file_id == SourceFile.id)
            .where(CodeEntity.id == entity_id)
        )

        result = await self.session.execute(stmt)
        row = result.first()

        if not row:
            raise ValueError(f"Entity {entity_id} not found")

        entity, source_file = row

        # Read file content to get the snippet
        # Ideally we should store content in CodeEntity, but if not, read file
        # Check if entity has content populated (we added content column to ExtractedEntity but did we add it to DB model?)
        # Let's check models.py... CodeEntity doesn't have `content` column in current models.py snippet I touched.
        # It has `start_line` / `end_line`.
        # So we must read from SourceFile (on disk).

        try:
            full_path = source_file.repository.local_path + "/" + source_file.path
            # Check if repo path is absolute or relative?
            # In IndexingService: local_path=path.

            # Simple fallback if file read fails
            code_snippet = f"# Code for {entity.full_name}"

            if os.path.exists(full_path):
                with open(full_path) as f:
                    lines = f.readlines()
                    # 1-based indexing in DB
                    start = max(0, entity.start_line - 1)
                    end = min(len(lines), entity.end_line)
                    code_snippet = "".join(lines[start:end])
        except Exception as e:
            logger.warning(f"Could not read source for wiki gen: {e}")
            code_snippet = i18n.get("prompts.domain_tools.wiki.source_unavailable")

        # 2. Prompt LLM
        prompt = i18n.get(
            "prompts.wiki.doc_generation",
            entity_name=entity.name,
            entity_type=entity.type,
            file_path=source_file.path,
            lang=entity.metadata.get("lang", ""),
            code_snippet=code_snippet,
        )
        messages = [
            SystemMessage(content="You generate clear, concise technical documentation."),
            HumanMessage(content=prompt)
        ]

        llm = LLMFactory.create_llm()
        response = await llm.ainvoke(messages)
        return response.content
