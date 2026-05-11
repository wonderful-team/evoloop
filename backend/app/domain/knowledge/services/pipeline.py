"""
Ingestion pipeline for processing document uploads.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import BinaryIO, Optional

from app.core import file as file_utils
from app.domain.knowledge.extractors import ExtractorRegistry
from app.domain.knowledge.models import (
    DocumentMetadata,
    ExtractionError,
    ExtractorInfo,
    MarkdownDocument,
)
from app.domain.knowledge.services.auto_tagger import get_auto_tagger
from app.domain.knowledge.services.search import get_fts_service, IndexDocumentRequest
from app.domain.knowledge.services.store import KnowledgeStoreService

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Pipeline for ingesting documents into the knowledge base.
    
    This pipeline coordinates:
    1. File type detection
    2. Extractor selection
    3. Content extraction (dehydration to Markdown)
    4. Metadata generation
    5. Storage
    
    Usage:
        pipeline = IngestionPipeline()
        
        with open("document.pdf", "rb") as f:
            result = await pipeline.process(
                file=f,
                filename="document.pdf",
                mime_type="application/pdf",
                collection="my-collection"
            )
    """
    
    def __init__(self, store: Optional[KnowledgeStoreService] = None):
        """
        Initialize the pipeline.
        
        Args:
            store: KnowledgeStoreService instance (creates default if None)
        """
        self.store = store or KnowledgeStoreService()
        
        # Ensure extractors are initialized
        # Note: In async context, call initialize() separately
    
    async def initialize(self) -> None:
        """Initialize extractors. Call this before first use."""
        ExtractorRegistry.initialize_defaults()
    
    async def process(
        self,
        file: BinaryIO,
        filename: str,
        mime_type: Optional[str] = None,
        collection: str = "default",
        custom_metadata: Optional[dict] = None,
        index_for_search: bool = True,
        index_for_vector_search: bool = True,
    ) -> "IngestionResult":
        """
        Process a file through the ingestion pipeline.
        
        Args:
            file: Binary file-like object
            filename: Original filename
            mime_type: MIME type (auto-detected if None)
            collection: Target collection name
            custom_metadata: Additional metadata to store
            index_for_search: Whether to index for full-text search
            index_for_vector_search: Whether to index for semantic vector search (T-3.1)
        
        Returns:
            IngestionResult with status and document info
        
        Raises:
            ExtractionError: If extraction fails
        """
        start_time = datetime.now(timezone.utc)
        saved_path = None
        
        try:
            # Step 1: Detect MIME type if not provided
            if not mime_type:
                mime_type = file_utils.guess_mime_type(filename)
                logger.debug(f"Detected MIME type: {mime_type}")
            
            # Step 2: Find appropriate extractor
            extractor = await ExtractorRegistry.get_extractor(mime_type, filename)
            
            if not extractor:
                return IngestionResult(
                    success=False,
                    error=f"No extractor available for {filename} ({mime_type})",
                    filename=filename,
                    mime_type=mime_type
                )
            
            logger.info(f"Using extractor '{extractor.name}' for {filename}")
            
            # Step 3: Extract content
            try:
                document = await extractor.extract(file, filename)
            except Exception as e:
                raise ExtractionError(
                    f"Extraction failed: {str(e)}",
                    source=filename,
                    details={"extractor": extractor.name}
                )
            
            # Step 4: Build metadata
            extraction_duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            metadata = DocumentMetadata(
                source_file=filename,
                source_mime_type=mime_type,
                file_size_bytes=self._get_file_size_from_obj(file),
                extracted_at=start_time,
                extractor=ExtractorInfo(
                    name=extractor.name,
                    version=extractor.version
                ),
                extraction_duration_ms=extraction_duration,
                title=document.metadata.get("title"),
                author=document.metadata.get("author"),
                language=document.metadata.get("language"),
                keywords=document.metadata.get("keywords", []),
                **(custom_metadata or {})
            )
            
            # Step 5: Save to store (run sync I/O in thread pool)
            save_result = await asyncio.to_thread(
                self.store.save_document,
                document=document,
                metadata=metadata,
                collection=collection
            )
            # Handle both dict and DocumentSaveResult
            if hasattr(save_result, "path"):
                saved_path = save_result.path
                save_title = getattr(save_result, "title", filename)
                save_size = getattr(save_result, "size", None)
                save_word_count = getattr(save_result, "word_count", None)
            else:
                saved_path = save_result["path"] if isinstance(save_result, dict) else save_result
                save_title = save_result.get("title", filename) if isinstance(save_result, dict) else filename
                save_size = save_result.get("size") if isinstance(save_result, dict) else None
                save_word_count = save_result.get("word_count") if isinstance(save_result, dict) else None
            
            # Step 6: Auto-tagging
            auto_tags = []
            if not custom_metadata or not custom_metadata.get("tags"):
                try:
                    tagger = get_auto_tagger()
                    tagging_result = await tagger.tag_document(
                        title=save_title,
                        content=document.content[:5000],  # First 5K chars for tagging
                        existing_tags=custom_metadata.get("tags") if custom_metadata else None
                    )
                    auto_tags = tagging_result.tags
                    logger.debug(f"Auto-tagged {filename} with: {auto_tags}")
                except Exception as e:
                    logger.warning(f"Auto-tagging failed for {filename}: {e}")
            
            # Merge auto-tags with provided tags
            all_tags = list(set((custom_metadata.get("tags", []) if custom_metadata else []) + auto_tags))
            
            # Step 7: Index for FTS search (async)
            if index_for_search:
                try:
                    fts = get_fts_service()
                    await fts.index_document(
                        IndexDocumentRequest(
                            doc_id=saved_path,
                            path=saved_path,
                            title=save_title,
                            content=document.content,
                            collection=collection or "default",
                            tags=all_tags,
                            file_size=save_size,
                            word_count=save_word_count,
                        )
                    )
                    logger.debug(f"Indexed {filename} for FTS search")
                except Exception as e:
                    logger.warning(f"Failed to index {filename} for FTS search: {e}")

            # Step 8: Index for vector semantic search (T-3.1)
            if index_for_vector_search:
                try:
                    from app.domain.knowledge.services.vector_search import get_kb_vector_service
                    vector_service = get_kb_vector_service()
                    await vector_service.index_document(
                        doc_id=saved_path,
                        title=save_title,
                        content=document.content,
                        collection=collection or "default",
                        tags=all_tags,
                    )
                    logger.debug(f"Indexed {filename} for vector search")
                except Exception as e:
                    logger.warning(f"Failed to index {filename} for vector search: {e}")
            
            logger.info(f"Successfully ingested {filename} to {saved_path}")
            
            return IngestionResult(
                success=True,
                path=saved_path,
                document=document,
                metadata=metadata,
                filename=filename,
                mime_type=mime_type,
                extractor_name=extractor.name
            )
        
        except ExtractionError:
            raise
        except Exception as e:
            logger.error(f"Ingestion failed for {filename}: {e}", exc_info=True)
            # Cleanup partial state
            if saved_path:
                try:
                    await asyncio.to_thread(self.store.delete_document, saved_path)
                    logger.debug(f"Cleaned up partial document: {saved_path}")
                except Exception as cleanup_err:
                    logger.warning(f"Failed to cleanup partial document: {cleanup_err}")
                try:
                    fts = get_fts_service()
                    await fts.remove_document(saved_path)
                except Exception:
                    pass
                try:
                    from app.domain.knowledge.services.vector_search import get_kb_vector_service
                    vector_service = get_kb_vector_service()
                    await vector_service.delete_document(saved_path)
                except Exception:
                    pass
            return IngestionResult(
                success=False,
                error=f"Ingestion failed: {str(e)}",
                filename=filename,
                mime_type=mime_type or "unknown"
            )
    
    async def process_upload(
        self,
        upload_file,  # FastAPI UploadFile
        collection: str = "default",
        doc_type: str = "doc",
        extract_metadata: bool = True,
        custom_metadata: Optional[dict] = None
    ) -> "IngestionResult":
        """
        Convenience method for processing FastAPI UploadFile.
        
        Args:
            upload_file: FastAPI UploadFile object
            collection: Target collection
            doc_type: Document type (doc, code, guide, etc.)
            extract_metadata: Whether to extract metadata
            custom_metadata: Additional metadata
        
        Returns:
            IngestionResult
        """
        # Get content type from upload
        mime_type = upload_file.content_type
        
        # Build custom metadata
        meta = custom_metadata or {}
        meta["doc_type"] = doc_type
        
        # Ensure file is at beginning
        await upload_file.seek(0)
        
        result = await self.process(
            file=upload_file.file,
            filename=upload_file.filename,
            mime_type=mime_type,
            collection=collection,
            custom_metadata=meta
        )
        
        return result
    
    async def batch_process(
        self,
        files: list[tuple[BinaryIO, str, Optional[str]]],
        collection: str = "default"
    ) -> list["IngestionResult"]:
        """
        Process multiple files in batch.
        
        Args:
            files: List of (file, filename, mime_type) tuples
            collection: Target collection
        
        Returns:
            List of IngestionResults
        """

        results = []
        for file, filename, mime_type in files:
            result = await self.process(file, filename, mime_type, collection)
            results.append(result)
        
        return results
    
    # ==========================================================================
    # Helpers
    # ==========================================================================
    
    def _get_file_size_from_obj(self, file: BinaryIO) -> int:
        """Get file size from file-like object."""
        try:
            current_pos = file.tell()
            file.seek(0, 2)
            size = file.tell()
            file.seek(current_pos)
            return size
        except Exception:
            return 0


class IngestionResult:
    """Result of an ingestion operation."""
    
    def __init__(
        self,
        success: bool,
        filename: str,
        mime_type: str,
        path: Optional[str] = None,
        document: Optional[MarkdownDocument] = None,
        metadata: Optional[DocumentMetadata] = None,
        error: Optional[str] = None,
        extractor_name: Optional[str] = None
    ):
        self.success = success
        self.filename = filename
        self.mime_type = mime_type
        self.path = path
        self.document = document
        self.metadata = metadata
        self.error = error
        self.extractor_name = extractor_name
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        result = {
            "success": self.success,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "path": self.path,
            "extractor": self.extractor_name
        }
        
        if self.error:
            result["error"] = self.error
        
        if self.metadata:
            result["metadata"] = {
                "title": self.metadata.title,
                "extractor": self.metadata.extractor.name,
                "duration_ms": self.metadata.extraction_duration_ms,
                "size_bytes": self.metadata.file_size_bytes
            }
        
        return result
