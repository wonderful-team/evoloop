"""
Knowledge Base Sync Service - Auto-sync project files to knowledge base.

Synchronizes README, Wiki, and other documentation files from workspace
projects to the knowledge base for Agent access.
"""

import logging
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
        Sync a project's README to knowledge base.

        Args:
            project_id: Workspace project ID
            project_path: Local path to project directory
            collection: Knowledge base collection name

        Returns:
            True if synced successfully
        """
        readme_paths = [
            Path(project_path) / "README.md",
            Path(project_path) / "readme.md",
            Path(project_path) / "README.rst",
            Path(project_path) / "README.txt",
        ]

        for readme_path in readme_paths:
            if readme_path.exists():
                try:
                    # Read and process README
                    with open(readme_path, "rb") as f:
                        content = f.read()

                    # Create a file-like object for pipeline
                    from io import BytesIO
                    file_obj = BytesIO(content)
                    file_obj.filename = f"project-{project_id}-README.md"

                    # Process through pipeline
                    result = await self.pipeline.process_upload(
                        file=file_obj,
                        collection=collection,
                        doc_type="doc",
                        extract_metadata=True
                    )

                    if result.success:
                        logger.info(f"Synced README for project {project_id}")
                        return True
                    else:
                        logger.warning(f"Failed to sync README: {result.error}")

                except Exception as e:
                    logger.error(f"Error syncing README for project {project_id}: {e}")

        return False

    async def sync_project_docs(
        self,
        project_id: int,
        project_path: str,
        patterns: list[str] = None
    ) -> dict:
        """
        Sync all project documentation files to knowledge base.

        Args:
            project_id: Workspace project ID
            project_path: Local path to project directory
            patterns: List of glob patterns to match doc files

        Returns:
            Statistics about synced files
        """
        if patterns is None:
            patterns = [
                "**/*.md",
                "**/docs/**/*.md",
                "**/wiki/**/*.md",
            ]

        stats = {"synced": 0, "failed": 0, "skipped": 0}
        project_dir = Path(project_path)

        for pattern in patterns:
            for doc_path in project_dir.glob(pattern):
                if not doc_path.is_file():
                    continue

                try:
                    # Skip files in node_modules, .git, etc.
                    if any(part.startswith(".") or part == "node_modules"
                           for part in doc_path.parts):
                        stats["skipped"] += 1
                        continue

                    # TODO: Process and sync document
                    # This would need more logic to avoid duplicates
                    # and handle updates properly

                except Exception as e:
                    logger.warning(f"Failed to sync {doc_path}: {e}")
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
