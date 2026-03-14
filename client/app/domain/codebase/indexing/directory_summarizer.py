"""Directory Summarization - Server-only feature (Neo4j required).

This module is a stub in the client branch. Directory summarization
requires Neo4j graph database which is only available in server mode.
"""
import logging

logger = logging.getLogger(__name__)


class DirectorySummarizer:
    """
    Server-only feature: Recursive directory summarization using Neo4j.

    Client mode: This is a no-op stub.
    """

    async def summarize_directory(self, project_id: int, dir_path: str, recursive: bool = True):
        """Stub: Directory summarization requires server mode."""
        logger.debug("[DirectorySummarizer] Server-only feature, skipping in client mode")
        return None

    async def generate_summary(self, dir_path: str, child_summaries: list[str]) -> str:
        """Stub: Summary generation requires server mode."""
        return "Directory summarization requires server mode."


# Global Instance
directory_summarizer = DirectorySummarizer()
