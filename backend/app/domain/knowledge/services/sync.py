"""
Knowledge Base Sync Service - Auto-sync project files to knowledge base.

Synchronizes README, Wiki, and other documentation files from workspace
projects to the knowledge base for Agent access.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from app.domain.knowledge.services.pipeline import IngestionPipeline
from app.domain.knowledge.services.store import KnowledgeStoreService

logger = logging.getLogger(__name__)


class KnowledgeSyncService:
    """
    Service for syncing project files to knowledge base.

    Usage:
        sync_service = KnowledgeSyncService()

        # Sync a project's README
        await sync_service.sync_project_readme(project_id, project_path)

        # Sync all project docs
        await sync_service.sync_project_docs(project_id, project_path)
    """

    def __init__(self):
        self.pipeline = IngestionPipeline()
        self.store = KnowledgeStoreService()

    async def sync_project_readme(
        self,
        project_id: int,
        project_path: str,
        collection: str = "project-docs"
    ) -> bool:
        """
        Sync a project's README to knowledge base using unified file service.
        """
        from app.core.file import read_file
        
        readme_names = ["README.md", "readme.md", "README.rst", "README.txt"]
        
        for name in readme_names:
            full_path = os.path.join(project_path, name)
            if os.path.isfile(full_path):
                try:
                    # Read using unified service
                    result = read_file(full_path)
                    if not result.success:
                        continue
                        
                    content = result.content.encode("utf-8")

                    # Create a file-like object for pipeline
                    from io import BytesIO
                    file_obj = BytesIO(content)
                    file_obj.filename = f"project-{project_id}-{name}"

                    # Process through pipeline
                    res = await self.pipeline.process(
                        file=file_obj,
                        filename=file_obj.filename,
                        collection=collection,
                    )

                    if res.success:
                        logger.info(f"Synced {name} for project {project_id}")
                        return True
                    else:
                        logger.warning(f"Failed to sync {name}: {res.error}")

                except Exception as e:
                    logger.error(f"Error syncing {name} for project {project_id}: {e}")

        return False

    async def sync_project_docs(
        self,
        project_id: int,
        project_path: str,
        patterns: list[str] = None
    ) -> dict:
        """
        Sync all project documentation files to knowledge base.
        Uses unified FileTraverser to ensure ignore patterns are respected.
        """
        from app.core.file import walk_tree, read_file
        
        if patterns is None:
            # Note: FileTraverser handles deep walking. 
            # We filter by extensions or categories here if needed.
            doc_extensions = {".md", ".txt", ".pdf", ".rst"}
        else:
            doc_extensions = {p.lower() if p.startswith(".") else f".{p.lower()}" for p in patterns}

        stats = {"synced": 0, "failed": 0, "skipped": 0}
        
        # Use centralized traverser (respects .gitignore, node_modules, etc.)
        for full_path in walk_tree(project_path):
            ext = os.path.splitext(full_path)[1].lower()
            if ext not in doc_extensions:
                continue

            try:
                # Read using unified service
                result = read_file(full_path)
                if not result.success:
                    stats["failed"] += 1
                    continue
                
                filename = os.path.basename(full_path)
                content = result.content.encode("utf-8")
                
                from io import BytesIO
                file_obj = BytesIO(content)
                file_obj.filename = filename

                # Process through pipeline (Pipeline handles internal deduplication/storage)
                res = await self.pipeline.process(
                    file=file_obj,
                    filename=filename,
                    collection="project-docs",
                )

                if res.success:
                    stats["synced"] += 1
                else:
                    stats["failed"] += 1

            except Exception as e:
                logger.warning(f"Failed to sync {full_path}: {e}")
                stats["failed"] += 1

        return stats


# Singleton instance
_sync_service: Optional[KnowledgeSyncService] = None


def get_sync_service() -> KnowledgeSyncService:
    """Get or create sync service singleton."""
    global _sync_service
    if _sync_service is None:
        _sync_service = KnowledgeSyncService()
    return _sync_service
