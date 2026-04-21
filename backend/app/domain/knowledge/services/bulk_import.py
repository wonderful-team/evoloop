"""
Bulk import service for knowledge base.

Supports importing multiple files, ZIP archives, and directory structures.
"""

import io
import logging
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Optional

from pydantic import Field

from app.domain.knowledge.services.pipeline import IngestionPipeline
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class BulkImportError(DynamicBaseModel):
    """Error entry for a bulk import operation."""
    file: str
    error: str


class ArchiveValidationResult(DynamicBaseModel):
    """Result of archive validation."""
    valid: bool
    total_files: int = 0
    processable_files: int = 0
    total_size_bytes: int = 0
    compressed_size_bytes: int = 0
    sample_files: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class BulkImportResult(DynamicBaseModel):
    """Result of bulk import operation."""
    total_files: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[BulkImportError] = Field(default_factory=list)
    imported_paths: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        """Backward compatibility for existing code calling to_dict manually."""
        return {
            "total_files": self.total_files,
            "successful": self.successful,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": [e.model_dump() for e in self.errors[:10]],  # Limit errors returned
            "imported_paths": self.imported_paths[:20],  # Limit paths returned
            "duration_ms": self.duration_ms
        }


class BulkImportService:
    """
    Service for bulk importing documents into the knowledge base.
    
    Supports:
    - Multiple individual files
    - ZIP archives (preserves directory structure)
    - Directory uploads (when supported by client)
    
    Usage:
        service = BulkImportService()
        
        # Import ZIP
        with open("docs.zip", "rb") as f:
            result = await service.import_zip(f, project="my-project")
        
        # Import multiple files
        files = [(file1, "doc1.pdf"), (file2, "doc2.md")]
        result = await service.import_files(files, project="my-project")
    """
    
    # Supported archive formats
    ARCHIVE_EXTENSIONS = {'.zip', '.tar', '.tar.gz', '.tgz'}
    
    # Files to skip
    SKIP_PATTERNS = {
        '__pycache__', '.git', '.svn', '.hg',  # Version control
        'node_modules', 'vendor',  # Dependencies
        '.DS_Store', 'Thumbs.db',  # OS files
        '*.tmp', '*.temp', '*.log',  # Temp files
    }
    
    def __init__(self, pipeline: Optional[IngestionPipeline] = None):
        """
        Initialize bulk import service.
        
        Args:
            pipeline: IngestionPipeline instance (creates default if None)
        """
        self.pipeline = pipeline or IngestionPipeline()
    
    async def import_zip(
        self,
        file: BinaryIO,
        project: str = "default",
        preserve_structure: bool = True,
        skip_existing: bool = False
    ) -> BulkImportResult:
        """
        Import documents from a ZIP archive.
        
        Args:
            file: ZIP file bytes
            project: Target project
            preserve_structure: Keep directory structure from ZIP
            skip_existing: Skip files that already exist
        
        Returns:
            BulkImportResult with statistics
        """
        start_time = datetime.now(timezone.utc)
        result = BulkImportResult()
        
        try:
            # Stream ZIP contents to avoid memory overflow for large archives
            MAX_MEMORY_SIZE = 100 * 1024 * 1024  # 100MB threshold
            
            if hasattr(file, 'seek'):
                file.seek(0, 2)
                size = file.tell()
                file.seek(0)
            else:
                size = None
            
            if size and size > MAX_MEMORY_SIZE:
                # Large ZIP: write to temp file first
                import shutil
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
                shutil.copyfileobj(file, tmp)
                tmp.close()
                zip_stream = tmp.name
                use_temp = True
            else:
                # Small ZIP: keep in memory
                zip_bytes = file.read()
                zip_stream = io.BytesIO(zip_bytes)
                use_temp = False
            
            with zipfile.ZipFile(zip_stream, 'r') as zf:
                # ZIP bomb protection
                MAX_TOTAL_SIZE = 500 * 1024 * 1024  # 500MB total extracted
                MAX_FILE_COUNT = 1000
                MAX_FILE_SIZE = 50 * 1024 * 1024    # 50MB per file
                MAX_COMPRESSION_RATIO = 100

                # Filter valid files
                files_to_process = []
                total_compressed = 0
                total_uncompressed = 0
                for info in zf.infolist():
                    if self._should_process_file(info.filename):
                        files_to_process.append(info)
                        total_compressed += info.compress_size
                        total_uncompressed += info.file_size

                # Validate limits
                if len(files_to_process) > MAX_FILE_COUNT:
                    result.error = f"Too many files: {len(files_to_process)} (max {MAX_FILE_COUNT})"
                    return result
                if total_uncompressed > MAX_TOTAL_SIZE:
                    result.error = f"Extracted size too large: {total_uncompressed / 1024 / 1024:.1f}MB (max {MAX_TOTAL_SIZE / 1024 / 1024}MB)"
                    return result
                if total_compressed > 0 and total_uncompressed / total_compressed > MAX_COMPRESSION_RATIO:
                    result.error = f"Suspicious compression ratio: {total_uncompressed / total_compressed:.0f}x (max {MAX_COMPRESSION_RATIO}x)"
                    return result

                result.total_files = len(files_to_process)

                # Process each file
                for info in files_to_process:
                    try:
                        # Extract to temp file
                        with tempfile.NamedTemporaryFile(delete=False) as tmp:
                            tmp.write(zf.read(info.filename))
                            tmp_path = tmp.name
                        
                        try:
                            # Determine path within project
                            if preserve_structure:
                                # Remove leading directory if any
                                path_parts = info.filename.split('/')
                                if len(path_parts) > 1:
                                    relative_path = '/'.join(path_parts[1:])
                                else:
                                    relative_path = info.filename
                                
                                # Remove extension for markdown conversion
                                save_path = relative_path
                            else:
                                save_path = Path(info.filename).name
                            
                            # Check if already exists
                            if skip_existing:
                                # This would need store service to check
                                pass
                            
                            # Import file
                            with open(tmp_path, 'rb') as tmp_file:
                                ingest_result = await self.pipeline.process(
                                    file=tmp_file,
                                    filename=info.filename,
                                    project=project,
                                    custom_metadata={
                                        "imported_from": "zip",
                                        "original_path": info.filename
                                    }
                                )
                            
                            if ingest_result.success:
                                result.successful += 1
                                result.imported_paths.append(ingest_result.path)
                            else:
                                result.failed += 1
                                result.errors.append(
                                    BulkImportError(
                                        file=info.filename,
                                        error=ingest_result.error or "Unknown ingestion error"
                                    )
                                )

                        finally:
                            os.unlink(tmp_path)

                    except Exception as e:
                        result.failed += 1
                        result.errors.append(
                            BulkImportError(file=info.filename, error=str(e))
                        )

        except zipfile.BadZipFile:
            result.errors.append(BulkImportError(file="archive", error="Invalid ZIP file"))
        except Exception as e:
            result.errors.append(BulkImportError(file="archive", error=str(e)))
        finally:
            # Clean up temp ZIP file if created
            if 'use_temp' in locals() and use_temp and 'zip_stream' in locals() and isinstance(zip_stream, str):
                try:
                    os.unlink(zip_stream)
                except Exception:
                    pass
        
        result.duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        return result
    
    async def import_files(
        self,
        files: list[tuple[BinaryIO, str]],
        project: str = "default",
        doc_type: str = "doc"
    ) -> BulkImportResult:
        """
        Import multiple individual files.
        
        Args:
            files: List of (file_object, filename) tuples
            project: Target project
            doc_type: Document type for all files
        
        Returns:
            BulkImportResult with statistics
        """
        start_time = datetime.utcnow()
        result = BulkImportResult(total_files=len(files))
        
        for file_obj, filename in files:
            try:
                # Ensure file is at beginning
                if hasattr(file_obj, 'seek'):
                    file_obj.seek(0)
                
                ingest_result = await self.pipeline.process(
                    file=file_obj,
                    filename=filename,
                    project=project,
                    custom_metadata={
                        "doc_type": doc_type,
                        "imported_from": "bulk_upload"
                    }
                )
                
                if ingest_result.success:
                    result.successful += 1
                    result.imported_paths.append(ingest_result.path)
                else:
                    result.failed += 1
                    result.errors.append(
                        BulkImportError(
                            file=filename,
                            error=ingest_result.error or "Unknown ingestion error"
                        )
                    )

            except Exception as e:
                result.failed += 1
                result.errors.append(BulkImportError(file=filename, error=str(e)))
        
        result.duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        return result
    
    async def import_directory(
        self,
        directory_path: Path,
        project: str = "default",
        recursive: bool = True
    ) -> BulkImportResult:
        """
        Import all documents from a local directory.
        
        Args:
            directory_path: Path to local directory
            project: Target project
            recursive: Recurse into subdirectories
        
        Returns:
            BulkImportResult with statistics
        """
        start_time = datetime.utcnow()
        result = BulkImportResult()
        
        # Collect files
        files_to_process = []
        pattern = "**/*" if recursive else "*"
        
        for file_path in directory_path.glob(pattern):
            if file_path.is_file() and self._should_process_file(str(file_path)):
                files_to_process.append(file_path)
        
        result.total_files = len(files_to_process)
        
        # Process files
        for file_path in files_to_process:
            try:
                relative_path = file_path.relative_to(directory_path)
                
                with open(file_path, 'rb') as f:
                    ingest_result = await self.pipeline.process(
                        file=f,
                        filename=file_path.name,
                        project=project,
                        custom_metadata={
                            "imported_from": "directory",
                            "original_path": str(relative_path)
                        }
                    )
                
                if ingest_result.success:
                    result.successful += 1
                    result.imported_paths.append(ingest_result.path)
                else:
                    result.failed += 1
                    result.errors.append(
                        BulkImportError(
                            file=str(relative_path),
                            error=ingest_result.error or "Unknown ingestion error"
                        )
                    )

            except Exception as e:
                result.failed += 1
                result.errors.append(BulkImportError(file=str(file_path), error=str(e)))
        
        result.duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        return result
    
    def _should_process_file(self, filename: str) -> bool:
        """Check if file should be processed based on name/pattern."""
        # Skip hidden files
        if filename.startswith('.') or '/.' in filename:
            return False
        
        # Skip known directories/patterns
        for pattern in self.SKIP_PATTERNS:
            if pattern in filename:
                return False
        
        # Skip unsupported extensions
        skip_exts = {'.exe', '.dll', '.so', '.dylib', '.bin'}
        if any(filename.lower().endswith(ext) for ext in skip_exts):
            return False
        
        return True
    
    def validate_archive(self, file: BinaryIO) -> ArchiveValidationResult:
        """
        Validate a ZIP archive before import.

        Returns:
            ArchiveValidationResult with validation info
        """
        try:
            file.seek(0)
            zip_bytes = file.read()
            file.seek(0)

            with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                files = [info.filename for info in zf.infolist() if not info.is_dir()]
                total_size = sum(info.file_size for info in zf.infolist())
                compressed_size = sum(info.compress_size for info in zf.infolist())

                # Count processable files
                processable = [f for f in files if self._should_process_file(f)]

                return ArchiveValidationResult(
                    valid=True,
                    total_files=len(files),
                    processable_files=len(processable),
                    total_size_bytes=total_size,
                    compressed_size_bytes=compressed_size,
                    sample_files=processable[:10]
                )

        except zipfile.BadZipFile:
            return ArchiveValidationResult(valid=False, error="Invalid ZIP file")
        except Exception as e:
            return ArchiveValidationResult(valid=False, error=str(e))
