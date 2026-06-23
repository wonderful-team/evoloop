import json
import logging
import os

from sqlalchemy import func, select, text

from app.infrastructure.database.sql.database import session_scope
from app.models.codebase import CodeEntity, CodeRelation, Repository, SourceFile

logger = logging.getLogger(__name__)


class OntologyBuilder:
    """
    Infers High-Level Semantic Relationships (Ontology) from SQL code_relation data.
    Outputs JSON files to .evoloop/ontology/ per project.
    """

    async def infer_relationships(self, project_path: str, project_id: int):
        deps = await self._compute_directory_dependencies(project_id)
        out_dir = os.path.join(project_path, ".evoloop", "ontology")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "dependencies.json")
        with open(out_path, "w") as f:
            json.dump(deps, f, indent=2)
        for (src, tgt), count in deps.items():
            logger.info(f"Architecture: {src} DEPENDS_ON {tgt} (Weight: {count})")

    async def _compute_directory_dependencies(self, project_id: int) -> dict[str, int]:
        async with session_scope() as session:
            stmt = select(
                SourceFile.path.label("src_path"),
            ).select_from(CodeRelation).join(
                CodeEntity, CodeRelation.source_entity_id == CodeEntity.id,
            ).join(
                SourceFile, CodeEntity.source_file_id == SourceFile.id,
            ).join(
                Repository, SourceFile.repository_id == Repository.id,
            ).where(Repository.project_id == project_id)

            src_paths = (await session.execute(stmt)).scalars().all()

            stmt2 = select(
                SourceFile.path.label("tgt_path"),
            ).select_from(CodeRelation).join(
                CodeEntity, CodeRelation.target_entity_id == CodeEntity.id,
            ).join(
                SourceFile, CodeEntity.source_file_id == SourceFile.id,
            ).join(
                Repository, SourceFile.repository_id == Repository.id,
            ).where(Repository.project_id == project_id)

            tgt_paths = (await session.execute(stmt2)).scalars().all()

        dep_map: dict[str, int] = {}
        for src, tgt in zip(src_paths, tgt_paths):
            src_dir = self._get_module_dir(src)
            tgt_dir = self._get_module_dir(tgt)
            if src_dir and tgt_dir and src_dir != tgt_dir:
                key = f"{src_dir} -> {tgt_dir}"
                dep_map[key] = dep_map.get(key, 0) + 1
        return {k: v for k, v in dep_map.items() if v >= 3}

    def _get_module_dir(self, file_path: str) -> str:
        if "/" not in file_path:
            return ""
        return file_path.rsplit("/", 1)[0]


ontology_builder = OntologyBuilder()
