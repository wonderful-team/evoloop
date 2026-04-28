"""
ContentIndexer: Handles code extraction and embedding generation.
"""
import logging

from pydantic import BaseModel, ConfigDict

from app.domain.codebase.indexing.base import (
    Document,
    ExtractedEntity,
    ExtractedRelation,
)
from app.domain.codebase.indexing.extractors.treesitter_extractor import (
    TreeSitterExtractor,
)
from app.infrastructure.embeddings.base import BaseEmbedder
from app.infrastructure.embeddings.factory import EmbedderFactory
from app.domain.codebase.schemas import IndexedContent

logger = logging.getLogger(__name__)


class ContentIndexer:
    """
    Indexes file content by:
    - Extracting code structure (TreeSitter)
    - Generating vector embeddings
    """

    def __init__(self, extractor: TreeSitterExtractor = None, embedder: BaseEmbedder = None):
        self.extractor = extractor or TreeSitterExtractor()
        self.embedder = embedder or EmbedderFactory.get_embedder()

    async def index(
        self,
        file_path: str,
        content: str,
        rel_path: str
    ) -> IndexedContent | None:
        """
        Extract and embed file content.

        Returns:
            IndexedContent if extraction succeeded, None if no data extracted.
        """
        # Extract
        extraction_result = await self.extractor.extract(file_path, content, module_path=rel_path)

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
            if len(content.strip()) > 50:
                logger.warning(f"Safe Indexing: Skipping {rel_path} - non-empty content but no extracted data.")
                return None

        # Create whole-file summary document
        file_summary_content = content
        if len(content) > 15000:
            file_summary_content = content[:15000] + "\n...(truncated)"

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

        # Prepend to docs
        all_docs = [file_summary_doc] + docs

        # Generate embeddings
        if all_docs:
            texts = []
            for d in all_docs:
                skel = d.metadata.get("skeleton")
                if skel:
                    texts.append(skel)
                else:
                    texts.append(d.content[:8000])  # Safety cap

            embeddings = await self.embedder.embed_documents(texts)
        else:
            embeddings = []

        return IndexedContent(
            documents=all_docs,
            entities=entities,
            relations=relations,
            embeddings=embeddings,
            file_summary_doc=file_summary_doc
        )
