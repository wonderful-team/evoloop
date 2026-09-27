import json
import os

from app.core.file import FileStatus, read_file

_SUMMARY_DIR = ".evoloop/directory_summaries"


class DirectorySummarizer:
    """Provides cached directory summaries persisted as JSON files."""

    @staticmethod
    def _summary_path(project_path: str, dir_path: str) -> str:
        safe = dir_path.strip("/").replace("/", "_") or "root"
        return os.path.join(project_path, _SUMMARY_DIR, f"{safe}.json")

    @staticmethod
    async def get_summary(project_path: str, dir_path: str = "") -> str | None:
        sp = DirectorySummarizer._summary_path(project_path, dir_path)
        read_result = read_file(sp)
        if read_result.status == FileStatus.SUCCESS:
            try:
                data = json.loads(read_result.content)
                return data.get("summary")
            except (json.JSONDecodeError, TypeError, ValueError):
                return None
        return None
