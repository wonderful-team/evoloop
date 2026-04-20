"""
Knowledge Base API Routes.

Handles document upload, retrieval, and management for the Agent knowledge base.
"""

import logging
from typing import Optional, Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile

from app.api.responses import BaseAPIResponse, ListResponse
from app.domain.knowledge.services.bulk_import import BulkImportService
from app.domain.knowledge.services.citations import get_citation_tracker
from app.domain.knowledge.services.deduplication import DeduplicationService
from app.domain.knowledge.services.pipeline import IngestionPipeline
from app.domain.knowledge.services.search import get_fts_service
from app.domain.knowledge.services.store import DocumentListItem, KnowledgeStoreService
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.base import SearchResponse

logger = logging.getLogger(__name__)

router = APIRouter()
pipeline = IngestionPipeline()
store = KnowledgeStoreService()
bulk_import = BulkImportService(pipeline)


# ============ Schemas ============

class DocumentResponse(BaseAPIResponse):
    """Response for document operations."""
    path: Optional[str] = None
    document: Optional[dict] = None


class DocumentListResponse(ListResponse[DocumentListItem]):
    """Response for listing documents."""
    documents: list[DocumentListItem]
    collections: list[str]


class DocumentMetadataResponse(BaseAPIResponse):
    """Structured metadata for a document chunk/response."""
    title: str | None = None
    source_file: str | None = None
    source_mime_type: str | None = None
    file_size_bytes: int | None = None
    extracted_at: str | None = None
    source_project_id: int | None = None


class DocumentContentResponse(BaseAPIResponse):
    """Response for reading document content."""
    path: str
    content: str
    metadata: DocumentMetadataResponse
    offset: int
    limit: int
    total_lines: int
    has_more: bool


class CollectionResponse(BaseAPIResponse):
    """Response for listing collections."""
    collections: list[str]
    stats: dict[str, Any]


class TagItem(DynamicBaseModel):
    """Single tag with document count."""
    name: str
    count: int


class TagResponse(BaseAPIResponse):
    """Response for listing tags."""
    tags: list[TagItem]
    total: int


class DocumentSearchItem(DynamicBaseModel):
    """Single document search result."""
    path: str
    match_count: int
    matches: list[dict[str, Any]]


class DocumentSearchResponse(SearchResponse):
    """Response for document search."""
    results: list[DocumentSearchItem]


class BulkUploadResponse(BaseAPIResponse):
    """Response for bulk upload."""
    pass


class ZipImportResponse(BaseAPIResponse):
    """Response for ZIP import."""
    pass


class FTSSearchResult(DynamicBaseModel):
    """Single FTS search result."""
    doc_id: str
    path: str
    collection: str | None
    title: str
    snippet: str
    highlights: list[str]
    score: float


class FTSSearchResponse(SearchResponse):
    """Response for FTS search."""
    results: list[FTSSearchResult]
    facets: dict[str, Any]


class FTSSuggestResponse(BaseAPIResponse):
    """Response for FTS suggestions."""
    suggestions: list[str]


# ============ Routes ============

@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(..., description="Document to upload"),
    collection: str = Form(default="default", description="Collection name"),
    doc_type: str = Form(default="doc", description="Document type (doc, code, guide, etc.)"),
    extract_metadata: bool = Form(default=True, description="Extract metadata automatically")
):
    """
    Upload a document to the knowledge base.
    
    The document will be extracted to Markdown format and stored in the
    knowledge base for Agent access via kb_read, kb_search, kb_list tools.
    
    Supported formats:
    - Text: .txt, .md, .rst
    - Code: .py, .js, .ts, .java, etc.
    - Web: .html, .htm
    - Office: .pdf (OCR-based), .docx
    - Images: .png, .jpg (OCR-based)
    """
    try:
        result = await pipeline.process_upload(
            file=file,
            collection=collection,
            doc_type=doc_type,
            extract_metadata=extract_metadata
        )
        
        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)
        
        return DocumentResponse(
            success=True,
            message=f"Document uploaded successfully",
            path=result.path,
            document=result.metadata
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    collection: Optional[str] = Query(None, description="Filter by collection"),
    pattern: str = Query("*.md", description="File pattern"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    source_project_id: Optional[int] = Query(None, description="Filter by workspace project ID"),
    limit: int = Query(50, ge=1, le=200)
):
    """
    List documents in the knowledge base.
    
    Returns a paginated list of documents with metadata.
    Supports filtering by collection, tags, and workspace project.
    """
    try:
        documents = store.list_documents(collection, pattern, source_project_id)
        
        # Filter by tags if specified
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            documents = [
                doc for doc in documents
                if any(tag in doc.tags for tag in tag_list)
            ]
        
        collections = store.list_collections()
        
        return DocumentListResponse(
            total=len(documents),
            documents=documents[:limit],
            collections=collections
        )
    
    except Exception as e:
        logger.error(f"List documents failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")


@router.get("/documents/{path:path}", response_model=DocumentContentResponse)
async def read_document(
    path: str,
    offset: int = Query(0, ge=0, description="Line offset (0-based)"),
    limit: int = Query(100, ge=1, le=500, description="Max lines to read")
):
    """
    Read a document from the knowledge base.
    
    Supports pagination via offset and limit parameters.
    Use has_more flag to determine if there's more content.
    """
    try:
        result = store.read_document(path, offset=offset, limit=limit)
        
        return DocumentContentResponse(
            path=path,
            content=result.content,
            metadata=DocumentMetadataResponse.model_validate(result.extracted_metadata or {}),
            offset=result.offset,
            limit=result.limit or 0,
            total_lines=result.total_lines,
            has_more=result.has_more
        )
    
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Document not found: {path}")
    
    except Exception as e:
        logger.error(f"Read document failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read document: {str(e)}")


@router.delete("/documents/{path:path}", response_model=DocumentResponse)
async def delete_document(path: str):
    """
    Delete a document from the knowledge base.
    """
    try:
        deleted = store.delete_document(path)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Document not found: {path}")
        
        return DocumentResponse(success=True, message=f"Document deleted: {path}")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete document failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


@router.get("/collections", response_model=CollectionResponse)
async def list_collections():
    """List all knowledge base collections."""
    try:
        collections = store.list_collections()
        stats = store.get_stats()
        
        return CollectionResponse(
            collections=collections,
            stats=stats
        )
    
    except Exception as e:
        logger.error(f"List collections failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list collections: {str(e)}")


@router.post("/collections/{name}", response_model=DocumentResponse)
async def create_collection(name: str):
    """Create a new knowledge base collection."""
    try:
        store.create_collection(name)
        return DocumentResponse(success=True, message=f"Collection created: {name}")
    
    except Exception as e:
        logger.error(f"Create collection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create collection: {str(e)}")


@router.get("/tags", response_model=TagResponse)
async def list_tags(
    collection: Optional[str] = Query(None, description="Filter by collection"),
    limit: int = Query(100, ge=1, le=500)
):
    """
    List all tags in the knowledge base.
    
    Returns tags with document counts for the tag cloud/filter UI.
    """
    try:
        fts = get_fts_service()
        tags, total = await fts.list_tags(collection=collection, limit=limit)
        
        return TagResponse(
            tags=[TagItem(name=t["name"], count=t["count"]) for t in tags],
            total=total
        )
    
    except Exception as e:
        logger.error(f"List tags failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list tags: {str(e)}")


@router.get("/search", response_model=DocumentSearchResponse)
async def search_documents(
    q: str = Query(..., description="Search query"),
    collection: Optional[str] = Query(None, description="Limit to collection"),
    context_lines: int = Query(2, ge=0, le=5)
):
    """
    Search documents in the knowledge base.
    
    Performs full-text search across all documents.
    """
    try:
        results = list(store.search_documents(q, collection, context_lines))
        
        return DocumentSearchResponse(
            query=q,
            results=results,
            total=sum(r.get("match_count", 0) for r in results)
        )
    
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/bulk-upload", response_model=BulkUploadResponse)
async def bulk_upload(
    files: list[UploadFile] = File(..., description="Multiple files to upload"),
    collection: str = Form(default="default", description="Collection name"),
    doc_type: str = Form(default="doc", description="Document type")
):
    """
    Upload multiple documents at once.
    
    Supports uploading multiple files in a single request.
    Each file is processed independently.
    """
    try:
        # Convert UploadFiles to tuples
        file_tuples = []
        for upload_file in files:
            await upload_file.seek(0)
            file_tuples.append((upload_file.file, upload_file.filename))
        
        result = await bulk_import.import_files(
            files=file_tuples,
            collection=collection,
            doc_type=doc_type
        )
        
        # Note: result.to_dict() fields are dropped from structured response to keep schema stable.
        return BulkUploadResponse(
            success=result.failed == 0,
            message=f"Imported {result.successful}/{result.total_files} files"
        )
    
    except Exception as e:
        logger.error(f"Bulk upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk upload failed: {str(e)}")


@router.post("/import-zip", response_model=ZipImportResponse)
async def import_zip(
    file: UploadFile = File(..., description="ZIP archive containing documents"),
    collection: str = Form(default="default", description="Collection name"),
    preserve_structure: bool = Form(default=True, description="Preserve directory structure")
):
    """
    Import documents from a ZIP archive.
    
    Extracts and processes all supported documents from the ZIP file.
    Directory structure can be preserved or flattened.
    """
    try:
        # Validate first
        await file.seek(0)
        validation = bulk_import.validate_archive(file.file)
        
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=validation["error"])
        
        # Process archive
        await file.seek(0)
        result = await bulk_import.import_zip(
            file=file.file,
            collection=collection,
            preserve_structure=preserve_structure
        )
        
        return ZipImportResponse(
            success=result.failed == 0,
            message=f"Imported {result.successful}/{result.total_files} files from ZIP"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ZIP import failed: {e}")
        raise HTTPException(status_code=500, detail=f"ZIP import failed: {str(e)}")


@router.post("/validate-zip")
async def validate_zip(
    file: UploadFile = File(..., description="ZIP archive to validate")
):
    """
    Validate a ZIP archive before import.
    
    Returns information about the archive contents without importing.
    """
    try:
        await file.seek(0)
        validation = bulk_import.validate_archive(file.file)
        await file.seek(0)
        
        return validation
    
    except Exception as e:
        logger.error(f"ZIP validation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


# ============ FTS Search ============

@router.get("/fts/search", response_model=FTSSearchResponse)
async def fts_search(
    q: str = Query(..., description="FTS5 search query"),
    collection: Optional[str] = Query(None, description="Filter by collection"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    source_project_id: Optional[int] = Query(None, description="Filter by workspace project ID"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Full-text search using SQLite FTS5.
    
    Supports FTS5 query syntax:
    - Simple: "authentication"
    - Phrase: '"JWT token"'
    - AND/OR: "auth AND token", "auth OR oauth"
    - Prefix: "auth*"
    """
    try:
        fts = get_fts_service()
        tag_list = tags.split(",") if tags else None
        
        results = await fts.search(
            query=q,
            collection=collection,
            tags=tag_list,
            limit=limit,
            offset=offset
        )
        
        return FTSSearchResponse(
            query=q,
            total=results.total,
            results=[
                FTSSearchResult(
                    doc_id=r.doc_id,
                    path=r.path,
                    collection=r.collection,
                    title=r.title,
                    snippet=r.content_snippet,
                    highlights=r.highlights,
                    score=r.bm25_score
                )
                for r in results.results
            ],
            facets=results.facets
        )
    
    except Exception as e:
        logger.error(f"FTS search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/fts/suggest", response_model=FTSSuggestResponse)
async def fts_suggest(
    prefix: str = Query(..., description="Search prefix"),
    collection: Optional[str] = Query(None, description="Filter by collection"),
    limit: int = Query(10, ge=1, le=20)
):
    """Get search suggestions based on prefix."""
    try:
        fts = get_fts_service()
        suggestions = await fts.suggest(prefix, collection, limit)
        return FTSSuggestResponse(suggestions=suggestions)
    
    except Exception as e:
        logger.error(f"Suggestions failed: {e}")
        raise HTTPException(status_code=500, detail=f"Suggestions failed: {str(e)}")


# ============ Deduplication ============

@router.get("/analytics/duplicates")
async def analyze_duplicates(
    collection: Optional[str] = Query(None, description="Collection to analyze")
):
    """
    Analyze documents for duplicates and near-duplicates.
    
    Returns groups of similar documents and suggested merges.
    """
    try:
        dedup = DeduplicationService(store)
        report = await dedup.analyze_collection(collection)
        return report.to_dict()
    
    except Exception as e:
        logger.error(f"Duplicate analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/merge")
async def merge_documents(
    source_paths: list[str],
    target_path: Optional[str] = None,
    strategy: str = "concatenate"
):
    """Merge multiple documents into one."""
    try:
        dedup = DeduplicationService(store)
        result = await dedup.merge_documents(source_paths, target_path, strategy)
        return result
    
    except Exception as e:
        logger.error(f"Merge failed: {e}")
        raise HTTPException(status_code=500, detail=f"Merge failed: {str(e)}")


# ============ Citation Analytics ============

@router.get("/analytics/popular")
async def get_popular_documents(
    collection: Optional[str] = Query(None, description="Filter by collection"),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50)
):
    """Get most cited/popular documents."""
    try:
        tracker = get_citation_tracker()
        from datetime import datetime, timedelta
        
        since = datetime.now() - timedelta(days=days)
        docs = await tracker.get_most_cited(collection, limit, since)
        
        return {
            "period_days": days,
            "documents": [
                {
                    "path": d.doc_path,
                    "citations": d.total_citations,
                    "unique_sessions": d.unique_sessions,
                    "last_accessed": d.last_accessed,
                    "tools_used": d.tools_used
                }
                for d in docs
            ]
        }
    
    except Exception as e:
        logger.error(f"Popular docs failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get popular docs: {str(e)}")


@router.get("/analytics/usage")
async def get_usage_analytics(
    days: int = Query(30, ge=1, le=365)
):
    """Get knowledge base usage analytics."""
    try:
        tracker = get_citation_tracker()
        analytics = await tracker.get_usage_analytics(days)
        return analytics
    
    except Exception as e:
        logger.error(f"Usage analytics failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {str(e)}")


@router.get("/recommendations")
async def get_recommendations(
    path: str = Query(..., description="Reference document path")
):
    """Get document recommendations based on citation patterns."""
    try:
        tracker = get_citation_tracker()
        recommendations = await tracker.get_recommendations(path)
        return {"recommendations": recommendations}
    
    except Exception as e:
        logger.error(f"Recommendations failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get recommendations: {str(e)}")


@router.get("/{path:path}/stats")
async def get_document_stats(path: str):
    """Get citation statistics for a specific document."""
    try:
        tracker = get_citation_tracker()
        stats = await tracker.get_document_stats(path)

        if not stats:
            return {"found": False, "message": "No citation data for this document"}

        return {
            "found": True,
            "path": stats.doc_path,
            "total_citations": stats.total_citations,
            "unique_sessions": stats.unique_sessions,
            "last_accessed": stats.last_accessed,
            "tools_used": stats.tools_used,
            "related_documents": stats.related_docs
        }

    except Exception as e:
        logger.error(f"Document stats failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


# ============ Auto Maintenance ============

@router.post("/maintenance/run")
async def run_maintenance(
    collection: Optional[str] = Query(None, description="Target collection"),
    dry_run: bool = Query(True, description="Preview changes without applying"),
    level: str = Query("medium", description="Maintenance level: light, medium, deep")
):
    """
    Run knowledge base maintenance tasks.

    Levels:
    - light: Analysis only, no changes
    - medium: Merge duplicates, archive cold docs
    - deep: Full optimization including knowledge graph
    """
    try:
        from app.domain.knowledge.services import run_manual_maintenance

        report = await run_manual_maintenance(
            collection=collection,
            dry_run=dry_run,
            level=level
        )

        return {
            "success": True,
            "dry_run": dry_run,
            "level": level,
            "report": report
        }

    except Exception as e:
        logger.error(f"Maintenance failed: {e}")
        raise HTTPException(status_code=500, detail=f"Maintenance failed: {str(e)}")


@router.get("/maintenance/duplicates")
async def analyze_maintenance_duplicates(
    collection: Optional[str] = Query(None, description="Target collection")
):
    """Analyze and return duplicate document report."""
    try:
        from app.domain.knowledge.services.deduplication import DeduplicationService

        service = DeduplicationService()
        report = await service.analyze_project(collection)

        return report.to_dict()

    except Exception as e:
        logger.error(f"Duplicate analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/maintenance/merge")
async def merge_maintenance_documents(
    paths: list[str] = Body(..., description="Document paths to merge"),
    strategy: str = Query("deduplicate", description="Merge strategy: concatenate, deduplicate"),
    target_path: Optional[str] = Query(None, description="Target path for merged document")
):
    """Merge multiple documents into one."""
    try:
        from app.domain.knowledge.services.deduplication import DeduplicationService

        service = DeduplicationService()
        result = await service.merge_documents(paths, target_path, strategy)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Merge failed"))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Merge failed: {e}")
        raise HTTPException(status_code=500, detail=f"Merge failed: {str(e)}")


@router.get("/maintenance/quality")
async def check_quality(
    collection: Optional[str] = Query(None, description="Target collection"),
    limit: int = Query(50, description="Maximum documents to check")
):
    """Check document quality and return report."""
    try:
        from app.domain.knowledge.services.auto_maintenance import QualityChecker

        checker = QualityChecker()
        results = await checker.scan_collection(collection)

        # Sort by score (lowest first) and limit
        results = sorted(results, key=lambda x: x.score)[:limit]

        return {
            "total_checked": len(results),
            "low_quality_count": sum(1 for r in results if r.score < 0.5),
            "documents": [
                {
                    "path": r.path,
                    "score": r.score,
                    "issues": r.issues,
                    "suggestions": r.suggestions
                }
                for r in results
            ]
        }

    except Exception as e:
        logger.error(f"Quality check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Quality check failed: {str(e)}")


@router.get("/maintenance/reports")
async def list_maintenance_reports(
    limit: int = Query(10, description="Number of recent reports")
):
    """List recent maintenance reports."""
    try:
        import json
        from pathlib import Path

        reports_dir = Path.home() / ".evoloop" / "knowledge" / "reports"

        if not reports_dir.exists():
            return {"reports": []}

        # Get all report files sorted by modification time
        report_files = sorted(
            reports_dir.glob("maintenance_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:limit]

        reports = []
        for filepath in report_files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    reports.append({
                        "filename": filepath.name,
                        "timestamp": data.get("timestamp"),
                        "duration_seconds": data.get("duration_seconds"),
                        "tasks_completed": data.get("tasks_completed", []),
                        "duplicates": data.get("duplicates", {}),
                        "summary": {
                            "duplicates_found": data.get("duplicates", {}).get("found", 0),
                            "low_quality_found": data.get("low_quality", {}).get("found", 0),
                            "cold_docs_found": data.get("cold_content", {}).get("found", 0),
                        }
                    })
            except Exception as e:
                logger.warning(f"Failed to read report {filepath}: {e}")

        return {"reports": reports}

    except Exception as e:
        logger.error(f"Failed to list reports: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list reports: {str(e)}")
