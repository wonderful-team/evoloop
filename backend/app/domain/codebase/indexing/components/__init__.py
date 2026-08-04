"""
Indexing Service Components.

This package contains the refactored components of IndexingService.

Components:
- FilePreparer: File filtering, reading, and validation
- ContentIndexer: Code extraction and embedding generation
- SQLPersister: SQL database persistence (Chunks, Entities, Relations)
"""

from app.domain.codebase.indexing.components.content_indexer import (
    ContentIndexer,
    IndexedContent,
)
from app.domain.codebase.indexing.components.file_preparer import (
    FilePreparer,
    PreparedFile,
)
from app.domain.codebase.indexing.components.sql_persister import SQLPersister

__all__ = [
    "FilePreparer",
    "PreparedFile",
    "ContentIndexer",
    "IndexedContent",
    "SQLPersister",
]
