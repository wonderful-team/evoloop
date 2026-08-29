"""
ContentIndexer: Handles code extraction and embedding generation.
"""

import logging

from app.domain.codebase.constants import (
    EMBEDDING_TEXT_CAP,
    FILE_SUMMARY_MAX_LENGTH,
    MIN_CONTENT_LENGTH_FOR_SAFE_INDEXING,
)
from app.domain.codebase.indexing.extractors.treesitter_extractor import (
    TreeSitterExtractor,
)
from app.domain.codebase.schemas import (
    Document,
    ExtractedEntity,
    ExtractedRelation,
    IndexedContent,
)
from app.infrastructure.embeddings.base import BaseEmbedder
from app.infrastructure.embeddings.factory import EmbedderFactory

logger = logging.getLogger(__name__)


class ContentIndexer:
    """
    Indexes file content by:
    - Extracting code structure (TreeSitter)
    - Generating vector embeddings
    """

    def __init__(
        self, extractor: TreeSitterExtractor = None, embedder: BaseEmbedder = None
    ):
        self.extractor = extractor or TreeSitterExtractor()
        self.embedder = embedder or EmbedderFactory.get_embedder()

    async def extract(
        self, file_path: str, content: str, rel_path: str
    ) -> (
        tuple[list[Document], list[ExtractedEntity], list[ExtractedRelation], Document]
        | None
    ):
        """
        Extract code structure without generating embeddings.

        Returns:
            (documents, entities, relations, file_summary_doc) or None if
            extraction produced no usable data.
        """
        extraction_result = await self.extractor.extract(
            file_path, content, module_path=rel_path
        )

        # Handle both list and ExtractionResult returns
        if isinstance(extraction_result, list):
            docs = extraction_result
            entities = []
            relations = []
        else:
            docs = extraction_result.documents
            entities = extraction_result.entities
            relations = extraction_result.relations

        # Safe indexing check
        if not docs and not entities:
            if len(content.strip()) > MIN_CONTENT_LENGTH_FOR_SAFE_INDEXING:
                logger.warning(
                    f"Safe Indexing: Skipping {rel_path} - non-empty content but no extracted data."
                )
                return None

        # Create whole-file summary document
        file_summary_content = content
        if len(content) > FILE_SUMMARY_MAX_LENGTH:
            file_summary_content = (
                content[:FILE_SUMMARY_MAX_LENGTH] + "\n...(truncated)"
            )

        file_line_count = content.count("\n") + 1
        file_summary_doc = Document(
            content=file_summary_content,
            metadata={
                "type": "file",
                "name": f"{rel_path}::whole_file",
                "start_line": 1,
                "end_line": file_line_count,
            },
        )

        all_docs = [file_summary_doc] + docs
        return all_docs, entities, relations, file_summary_doc

    async def index(
        self, file_path: str, content: str, rel_path: str
    ) -> IndexedContent | None:
        """
        Extract and embed file content.

        Returns:
            IndexedContent if extraction succeeded, None if no data extracted.
        """
        extracted = await self.extract(file_path, content, rel_path)
        if extracted is None:
            return None

        all_docs, entities, relations, file_summary_doc = extracted

        # Generate embeddings
        embeddings = []
        if all_docs and self.embedder is not None:
            texts = []
            for d in all_docs:
                skel = d.metadata.get("skeleton")
                if skel:
                    texts.append(skel)
                else:
                    texts.append(d.content[:EMBEDDING_TEXT_CAP])  # Safety cap

            try:
                embeddings = await self.embedder.embed_documents(texts)
            except Exception as e:
                logger.warning(
                    f"Embedding generation failed for {rel_path}: {e}. "
                    "Continuing indexing without embeddings.",
                    exc_info=True,
                )
                embeddings = [[] for _ in texts]

        return IndexedContent(
            documents=all_docs,
            entities=entities,
            relations=relations,
            embeddings=embeddings,
            file_summary_doc=file_summary_doc,
        )
