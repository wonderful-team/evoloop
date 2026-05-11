"""
Knowledge Base API Routes.

Handles document upload, retrieval, and management for the Agent knowledge base.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile

from app.api.responses import BaseAPIResponse
from app.api.schemas.knowledge import DocumentResponse, DocumentListResponse, DocumentMetadataResponse, \
    DocumentContentResponse, CollectionResponse, TagItem, TagResponse, DocumentSearchResponse, FTSSearchResult, \
    FTSSearchResponse, FTSSuggestResponse
from app.domain.knowledge.services.bulk_import import BulkImportService
from app.domain.knowledge.services.citations import get_citation_tracker
from app.domain.knowledge.services.deduplication import DeduplicationService
from app.domain.knowledge.services.pipeline import IngestionPipeline
from app.domain.knowledge.services.search import get_fts_service
from app.domain.knowledge.services.store import KnowledgeStoreService

logger = logging.getLogger(__name__)

router = APIRouter()
pipeline = IngestionPipeline()
store = KnowledgeStoreService()
bulk_import = BulkImportService(pipeline)


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
    result = await pipeline.process_upload(
        upload_file=file,
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
        document=result.metadata.model_dump(mode="json") if result.metadata else None
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    collection: Optional[str] = Query(None, description="Filter by collection"),
    pattern: str = Query("*.md", description="File pattern"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    source_project_id: Optional[int] = Query(None, description="Filter by workspace project ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List documents in the knowledge base.
    
    Returns a paginated list of documents with metadata.
    Supports filtering by collection, tags, and workspace project.
    """
    documents = store.list_documents(collection, pattern, source_project_id, limit=limit, offset=offset)
    # Filter by tags if specified (applied post-query for now)
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        documents = [
            doc for doc in documents
            if any(tag in doc.tags for tag in tag_list)
        ]
    collections = store.list_collections()
    return DocumentListResponse(
        total=len(documents),
        documents=documents,
        collections=collections
    )


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


@router.delete("/documents/{path:path}", response_model=DocumentResponse)
async def delete_document(path: str):
    """
    Delete a document from the knowledge base.
    """
    deleted = store.delete_document(path)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Document not found: {path}")
    # Clean up FTS and vector indexes
    try:
        fts = get_fts_service()
        await fts.remove_document(path)
    except (OSError, RuntimeError, TypeError, ValueError) as e:
        logger.warning(f"Failed to remove document from FTS index: {e}")
    try:
        from app.domain.knowledge.services.vector_search import get_kb_vector_service
        vector_service = get_kb_vector_service()
        await vector_service.delete_document(path)
    except (OSError, RuntimeError, TypeError, ValueError) as e:
        logger.warning(f"Failed to remove document from vector index: {e}")
    return DocumentResponse(success=True, message=f"Document deleted: {path}")


@router.get("/collections", response_model=CollectionResponse)
async def list_collections():
    """List all knowledge base collections."""
    collections = store.list_collections()
    stats = store.get_stats()
    return CollectionResponse(
        collections=collections,
        stats=stats
    )


@router.post("/collections/{name}", response_model=DocumentResponse)
async def create_collection(name: str):
    """Create a new knowledge base collection."""
    store.create_collections(name)
    return DocumentResponse(success=True, message=f"Collection created: {name}")


@router.get("/tags", response_model=TagResponse)
async def list_tags(
    collection: Optional[str] = Query(None, description="Filter by collection"),
    limit: int = Query(100, ge=1, le=500)
):
    """
    List all tags in the knowledge base.
    
    Returns tags with document counts for the tag cloud/filter UI.
    """
    fts = get_fts_service()
    tags, total = await fts.list_tags(collection=collection, limit=limit)
    return TagResponse(
        tags=[TagItem(name=t["name"], count=t["count"]) for t in tags],
        total=total
    )


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
    results = list(store.search_documents(q, collection, context_lines))
    return DocumentSearchResponse(
        query=q,
        results=results,
        total=sum(r.get("match_count", 0) for r in results)
    )


@router.post("/bulk-upload", response_model=BaseAPIResponse)
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
    return BaseAPIResponse(
        success=result.failed == 0,
        message=f"Imported {result.successful}/{result.total_files} files"
    )


@router.post("/import-zip", response_model=BaseAPIResponse)
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
    return BaseAPIResponse(
        success=result.failed == 0,
        message=f"Imported {result.successful}/{result.total_files} files from ZIP"
    )


@router.post("/validate-zip")
async def validate_zip(
    file: UploadFile = File(..., description="ZIP archive to validate")
):
    """
    Validate a ZIP archive before import.
    
    Returns information about the archive contents without importing.
    """
    await file.seek(0)
    validation = bulk_import.validate_archive(file.file)
    await file.seek(0)
    return validation


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


@router.get("/fts/suggest", response_model=FTSSuggestResponse)
async def fts_suggest(
    prefix: str = Query(..., description="Search prefix"),
    collection: Optional[str] = Query(None, description="Filter by collection"),
    limit: int = Query(10, ge=1, le=20)
):
    """Get search suggestions based on prefix."""
    fts = get_fts_service()
    suggestions = await fts.suggest(prefix, collection, limit)
    return FTSSuggestResponse(suggestions=suggestions)


@router.get("/analytics/duplicates")
async def analyze_duplicates(
    collection: Optional[str] = Query(None, description="Collection to analyze")
):
    """
    Analyze documents for duplicates and near-duplicates.
    
    Returns groups of similar documents and suggested merges.
    """
    dedup = DeduplicationService(store)
    report = await dedup.analyze_collection(collection)
    return report.to_dict()


@router.post("/merge")
async def merge_documents(
    source_paths: list[str],
    target_path: Optional[str] = None,
    strategy: str = "concatenate"
):
    """Merge multiple documents into one."""
    dedup = DeduplicationService(store)
    result = await dedup.merge_documents(source_paths, target_path, strategy)
    return result


@router.get("/analytics/popular")
async def get_popular_documents(
    collection: Optional[str] = Query(None, description="Filter by collection"),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50)
):
    """Get most cited/popular documents."""
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


@router.get("/analytics/usage")
async def get_usage_analytics(
    days: int = Query(30, ge=1, le=365)
):
    """Get knowledge base usage analytics."""
    tracker = get_citation_tracker()
    analytics = await tracker.get_usage_analytics(days)
    return analytics


@router.get("/recommendations")
async def get_recommendations(
    path: str = Query(..., description="Reference document path")
):
    """Get document recommendations based on citation patterns."""
    tracker = get_citation_tracker()
    recommendations = await tracker.get_recommendations(path)
    return {"recommendations": recommendations}


@router.get("/{path:path}/stats")
async def get_document_stats(path: str):
    """Get citation statistics for a specific document."""
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


@router.get("/maintenance/duplicates")
async def analyze_maintenance_duplicates(
    collection: Optional[str] = Query(None, description="Target collection")
):
    """Analyze and return duplicate document report."""
    from app.domain.knowledge.services.deduplication import DeduplicationService
    service = DeduplicationService()
    report = await service.analyze_project(collection)
    return report.to_dict()


@router.post("/maintenance/merge")
async def merge_maintenance_documents(
    paths: list[str] = Body(..., description="Document paths to merge"),
    strategy: str = Query("deduplicate", description="Merge strategy: concatenate, deduplicate"),
    target_path: Optional[str] = Query(None, description="Target path for merged document")
):
    """Merge multiple documents into one."""
    from app.domain.knowledge.services.deduplication import DeduplicationService
    service = DeduplicationService()
    result = await service.merge_documents(paths, target_path, strategy)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Merge failed"))
    return result


@router.get("/maintenance/quality")
async def check_quality(
    collection: Optional[str] = Query(None, description="Target collection"),
    limit: int = Query(50, description="Maximum documents to check")
):
    """Check document quality and return report."""
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


@router.get("/maintenance/reports")
async def list_maintenance_reports(
    limit: int = Query(10, description="Number of recent reports")
):
    """List recent maintenance reports from database."""
    reports = []
    # Try database first (T-1.4)
    try:
        from app.infrastructure.database.resource_manager import db_resource_manager
        from app.models.maintenance import MaintenanceReport
        from sqlalchemy import desc, select
        async with db_resource_manager.session_factory() as session:
            result = await session.execute(
                select(MaintenanceReport)
                .order_by(desc(MaintenanceReport.timestamp))
                .limit(limit)
            )
            rows = result.scalars().all()
            for row in rows:
                summary = {}
                try:
                    summary = json.loads(row.summary_json or "{}")
                except (json.JSONDecodeError, TypeError):
                    pass
                reports.append({
                    "id": row.id,
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                    "level": row.level,
                    "dry_run": bool(row.dry_run),
                    "duration_seconds": row.duration_seconds,
                    "summary": summary,
                })
    except (OSError, RuntimeError) as e:
        logger.warning(f"Failed to read reports from DB: {e}")
    # Fallback to JSON files if SQLite is empty
    if not reports:
        reports_dir = Path.home() / ".evoloop" / "knowledge" / "reports"
        if reports_dir.exists():
            report_files = sorted(
                reports_dir.glob("maintenance_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:limit]
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
                except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
                    logger.warning(f"Failed to read report {filepath}: {e}")
    return {"reports": reports}
