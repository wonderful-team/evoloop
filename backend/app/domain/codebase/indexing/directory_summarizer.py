import json
import logging
import os

from sqlalchemy import select

from app.infrastructure.database.sql.database import session_scope
from app.models.codebase import CodeChunk, Repository, SourceFile

logger = logging.getLogger(__name__)

_SUMMARY_DIR = ".evoloop/directory_summaries"


class DirectorySummarizer:
    """Summarizes directories using SQL data and persists to JSON files."""

    @staticmethod
    def _summary_path(project_path: str, dir_path: str) -> str:
        safe = dir_path.strip("/").replace("/", "_") or "root"
        return os.path.join(project_path, _SUMMARY_DIR, f"{safe}.json")

    async def summarize_directory(
        self, project_path: str, project_id: int, dir_path: str,
        recursive: bool = True, model: str | None = None,
    ) -> str:
        existing = await self.get_summary(project_path, dir_path)
        if existing:
            return existing

        children = await self._load_children(project_id, dir_path)
        if not children:
            return "Empty Directory"

        summary_text = await self.generate_summary(dir_path, children, model=model)

        os.makedirs(os.path.join(project_path, _SUMMARY_DIR), exist_ok=True)
        with open(self._summary_path(project_path, dir_path), "w") as f:
            json.dump({"path": dir_path, "summary": summary_text}, f)

        return summary_text

    @staticmethod
    async def get_summary(project_path: str, dir_path: str = "") -> str | None:
        sp = DirectorySummarizer._summary_path(project_path, dir_path)
        if os.path.exists(sp):
            try:
                with open(sp) as f:
                    data = json.load(f)
                    return data.get("summary")
            except Exception:
                pass
        return None

    async def _load_children(self, project_id: int, dir_path: str) -> list[dict]:
        prefix = dir_path.rstrip("/") + "/" if dir_path else ""
        async with session_scope() as session:
            stmt = select(SourceFile.path, CodeChunk.content).join(
                CodeChunk, CodeChunk.source_file_id == SourceFile.id, isouter=True
            ).where(
                SourceFile.repository_id.in_(
                    select(Repository.id).where(Repository.project_id == project_id)
                ),
                SourceFile.path.startswith(prefix),
                CodeChunk.chunk_type == "file",
            )
            rows = (await session.execute(stmt)).all()
        children = []
        seen_dirs = set()
        for path, content in rows:
            rel = path[len(prefix):] if prefix else path
            if "/" in rel:
                subdir = rel.split("/")[0]
                if subdir not in seen_dirs:
                    seen_dirs.add(subdir)
                    children.append({"type": "directory", "name": subdir})
            else:
                preview = (content or "")[:1000]
                children.append({"type": "file", "name": path, "content": preview})
        return children

    async def generate_summary(self, dir_path: str, child_summaries: list[dict], model: str | None = None) -> str:
        from app.utils import render_template
        prompt_text = render_template(
            "domain/codebase/directory_summary.prompt.j2",
            directory_path=dir_path,
            child_summaries=child_summaries,
        )
        from app.core.llm import InternalLLMService
        from app.infrastructure.config.service import SystemConfigService
        model_name = SystemConfigService.get_value("LLM_MODEL")
        response = await InternalLLMService.invoke(
            messages=[{"role": "user", "content": prompt_text}],
            purpose="skill_synthesis",
            model_name=model or model_name,
        )
        return response.content


directory_summarizer = DirectorySummarizer()
