import json
import logging
import os
import re

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core.config import settings
from app.core.evocloud import evocloud_manager
from app.core.file.service import filter_code_files, walk_tree
from app.domain.wiki.wiki_builder import WikiBuilder
from app.i18n.service import i18n
from app.infrastructure.database.resource_manager import db_resource_manager as rm
from app.models.wiki import WikiPage
from app.utils import render_template
from app.utils.file import normalize_path
from app.domain.tools.schemas import ExtractedConcept
from app.domain.wiki.schemas import ConceptExtractionResult, WikiPagePlan, WikiStructure, WikiValidationResult

logger = logging.getLogger(__name__)


# --- Pydantic models for structured LLM output ---


class WikiService:
    """
    Service for Wiki page management and generation.
    Integrates with MemoryService to extract and store knowledge concepts.
    """

    def get_pages(self, project_id: int) -> list[WikiPage]:
        with Session(rm.sync_engine) as session:
            statement = select(WikiPage).where(WikiPage.project_id == project_id).order_by(WikiPage.order)
            results = session.exec(statement)
            return results.all()

    def get_page(self, page_id: int) -> WikiPage | None:
        with Session(rm.sync_engine) as session:
            return session.get(WikiPage, page_id)

    def get_projects_with_wiki(self, project_ids: list[int]) -> set[int]:
        """
        Efficiently check which projects have wiki pages.
        """
        if not project_ids:
            return set()
        with Session(rm.sync_engine) as session:
            statement = select(WikiPage.project_id).where(
                WikiPage.project_id.in_(project_ids)
            ).distinct()
            results = session.exec(statement).all()
            return set(results)

    def _get_file_tree(self, root_path: str) -> str:
        """
        Generates a simplified file tree string using standard file utilities.
        """
        try:
            # 1. Get all valid file paths (absolute)
            all_files_abs = list(walk_tree(root_path))

            # 2. Convert to relative and normalize
            all_files_rel = []
            for f in all_files_abs:
                rel = os.path.relpath(f, root_path)
                all_files_rel.append(normalize_path(rel))

            # 3. Apply code file filtering
            valid_files = filter_code_files(all_files_rel)

            # 4. Build Tree String
            return self._paths_to_tree_string(valid_files)

        except Exception as e:
            logger.error(f"Error generating file tree: {e}")
            return "(Error generating file tree)"

    def _paths_to_tree_string(self, paths: list[str]) -> str:
        """
        Converts a list of file paths into a visual tree string.
        """
        paths.sort()
        lines = []
        prev_parts = []
        truncated = False

        for path in paths:
            parts = path.split("/")
            common_depth = 0
            for i in range(min(len(parts), len(prev_parts))):
                if parts[i] == prev_parts[i]:
                    common_depth += 1
                else:
                    break

            for i in range(common_depth, len(parts)):
                lines.append({
                    "indent": "  " * i,
                    "name": parts[i],
                    "is_dir": i < len(parts) - 1,
                })

            prev_parts = parts

            if len(lines) > 5000:
                truncated = True
                break

        return render_template(
            "domain/wiki/file_tree.prompt.j2",
            lines=lines,
            truncated=truncated
        )

    def _read_file_safe(self, path: str, max_chars: int = 50000) -> str:
        if not os.path.exists(path) or os.path.isdir(path):
            return ""
        try:
            with open(path, encoding='utf-8', errors='ignore') as f:
                return f.read(max_chars)
        except Exception as e:
            logger.warning(f"Failed to read file {path}: {e}")
            return ""

    async def _extract_and_store_concepts(
        self,
        page_title: str,
        page_content: str,
        project_id: int,
        model: str | None = None,
    ) -> list[str]:
        if not getattr(settings, 'WIKI_EXTRACT_CONCEPTS', True):
            return []

        try:
            builder = WikiBuilder()
            extraction_prompt = builder.build_concept_extraction_prompt(page_title, page_content)

            from app.core.llm import InternalLLMService
            from app.infrastructure.config.service import SystemConfigService
            model_name = SystemConfigService.get_value("LLM_MODEL")
            try:
                result = await InternalLLMService.invoke_structured(
                    messages=[{"role": "user", "content": extraction_prompt}],
                    purpose="memory_extraction",
                    output_schema=ConceptExtractionResult,
                    model_name=model_name,
                )
            except Exception:
                response = await InternalLLMService.invoke(
                    messages=[{"role": "user", "content": extraction_prompt}],
                    purpose="memory_extraction",
                    model_name=model or model_name,
                )
                json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
                if json_match:
                    result_dict = json.loads(json_match.group(0))
                    result = ConceptExtractionResult(**result_dict)
                else:
                    result = ConceptExtractionResult(concepts=[])

            stored_names = []
            if result and result.concepts:
                from app.core.memory.lifespan import MemoryLifespanManager
                if not MemoryLifespanManager.is_initialized():
                    await MemoryLifespanManager.ainitialize()
                container = MemoryLifespanManager.get_container()
                manager = container.memory_manager
                for concept in result.concepts[:5]:
                    from app.core.memory.models import Concept as MemConcept
                    mem_concept = MemConcept(name=concept.name, description=concept.description, project_id=project_id, related_files=[])
                    await manager.store_concept(mem_concept)
                    stored_names.append(concept.name)
                    logger.info(f"Wiki Concept Harvested: {concept.name}")

            return stored_names

        except Exception as e:
            logger.warning(f"Failed to extract concepts from wiki page '{page_title}': {e}")
            return []

    async def _validate_structure(
        self,
        structure_data: dict | WikiStructure,
        project_context: str,
    ) -> WikiStructure:
        try:
            builder = WikiBuilder()
            validation_prompt = builder.build_validation_prompt(
                structure_data.model_dump() if isinstance(structure_data, WikiStructure) else structure_data,
                project_context,
            )
            from app.core.llm import InternalLLMService
            from app.infrastructure.config.service import SystemConfigService
            model_name = SystemConfigService.get_value("LLM_MODEL")
            response = await InternalLLMService.invoke(
                messages=[{"role": "user", "content": validation_prompt}],
                purpose="task_analysis",
                model_name=model_name,
            )
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if not json_match:
                return WikiStructure.model_validate(structure_data)

            validation_result = WikiValidationResult.model_validate(json.loads(json_match.group(0)))
            if validation_result.is_complete or not validation_result.gaps:
                return WikiStructure.model_validate(structure_data)

            wiki_structure = WikiStructure.model_validate(structure_data)
            pages = list(wiki_structure.pages)
            for gap in validation_result.gaps:
                suggested_title = gap.suggested_title or gap.area or "Additional Page"
                slug = suggested_title.lower().replace(" ", "-").replace("_", "-")
                slug = re.sub(r'[^a-z0-9-]', '', slug)[:50]
                new_page = WikiPagePlan(
                    id=f"gap-{slug}",
                    title=suggested_title,
                    description=gap.reason,
                    relevant_files=[],
                    importance="medium",
                    children=[],
                )
                pages.append(new_page)
            wiki_structure.pages = pages
            return wiki_structure
        except Exception as e:
            logger.warning(f"Structure validation failed: {e}")
            return WikiStructure.model_validate(structure_data)

    async def generate_wiki(self, project_id: int, topic: str, force_regenerate: bool = False, model: str | None = None):
        logger.info(f"Starting Wiki Generation for project {project_id}")
        project_data = await evocloud_manager.get_project_by_id(project_id)
        if not project_data or not project_data.get('path'):
            return []
        project_path = project_data['path']

        if force_regenerate:
            from sqlmodel import delete
            with Session(rm.sync_engine) as session:
                statement = delete(WikiPage).where(WikiPage.project_id == project_id)
                session.exec(statement)
                session.commit()

        file_tree = self._get_file_tree(project_path)
        readme_content = self._read_file_safe(os.path.join(project_path, "README.md"))

        builder = WikiBuilder()
        structure_prompt = builder.build_structure_prompt(file_tree, readme_content)

        try:
            from app.core.llm import InternalLLMService
            from app.infrastructure.config.service import SystemConfigService
            model_name = SystemConfigService.get_value("LLM_MODEL")
            structure_response = await InternalLLMService.invoke(
                messages=[{"role": "user", "content": structure_prompt}],
                purpose="task_analysis",
                model_name=model_name,
            )
            json_match = re.search(r'\{.*\}', structure_response.content, re.DOTALL)
            if json_match:
                structure_data = WikiStructure.model_validate(json.loads(json_match.group(0)))
                pages_to_generate = structure_data.pages
            else:
                raise ValueError("No JSON found in response")
        except Exception as e:
            logger.error(f"Failed to determine wiki structure: {e}")
            pages_to_generate = [
                WikiPagePlan(id="overview", title=i18n.get("wiki.fallback.overview")),
                WikiPagePlan(id="architecture", title=i18n.get("wiki.fallback.architecture")),
                WikiPagePlan(id="setup", title=i18n.get("wiki.fallback.setup")),
            ]
            structure_data = WikiStructure(pages=pages_to_generate)

        project_context = f"Project path: {project_path}\nREADME preview: {readme_content[:500] if readme_content else 'No README'}"
        validated_structure = await self._validate_structure(structure_data=structure_data, project_context=project_context)
        pages_to_generate = validated_structure.pages
        saved_pages = []

        async def process_page_recursive(plan: WikiPagePlan, parent_id=None, order=0, model=None):
            page_title = plan.title or "Untitled"
            page_slug = plan.id or f"page-{order}"
            if not force_regenerate:
                with Session(rm.sync_engine) as session:
                    stmt = select(WikiPage).where(WikiPage.project_id == project_id, WikiPage.slug == page_slug)
                    existing_page = session.exec(stmt).first()
                    if existing_page and existing_page.content:
                        if existing_page.parent_id != parent_id or existing_page.order != order:
                            existing_page.parent_id = parent_id
                            existing_page.order = order
                            session.add(existing_page)
                            session.commit()
                        saved_pages.append(existing_page)
                        for i, child_plan in enumerate(plan.children):
                            await process_page_recursive(child_plan, parent_id=existing_page.id, order=i, model=model)
                        return

            files_to_read_content = {}
            relevant_files = plan.relevant_files or []
            for rel_path in relevant_files:
                full_path = os.path.join(project_path, rel_path)
                content = self._read_file_safe(full_path)
                if content:
                    files_to_read_content[rel_path] = content

            files_data = [{"path": p, "content": c} for p, c in files_to_read_content.items()]
            content_prompt = render_template("domain/wiki/wiki_context.prompt.j2", page_title=page_title, files=files_data, tree=file_tree)

            try:
                from app.core.llm import InternalLLMService
                from app.infrastructure.config.service import SystemConfigService
                model_name = SystemConfigService.get_value("LLM_MODEL")
                content_response = await InternalLLMService.invoke(
                    messages=[{"role": "user", "content": content_prompt}],
                    purpose="skill_synthesis",
                    model_name=model or model_name,
                )
                page_content = content_response.content
            except Exception as e:
                page_content = f"# {page_title}\n\nError: {e}"

            with Session(rm.sync_engine) as session:
                stmt = select(WikiPage).where(WikiPage.project_id == project_id, WikiPage.slug == page_slug)
                db_page = session.exec(stmt).first()
                if db_page:
                    db_page.content = page_content
                    db_page.title = page_title
                    db_page.order = order
                    db_page.parent_id = parent_id
                    session.add(db_page)
                else:
                    db_page = WikiPage(project_id=project_id, title=page_title, slug=page_slug, content=page_content, order=order, parent_id=parent_id)
                    session.add(db_page)
                session.commit()
                session.refresh(db_page)
                saved_pages.append(db_page)

            if page_content:
                await self._extract_and_store_concepts(page_title=page_title, page_content=page_content, project_id=project_id, model=model)

            for i, child_plan in enumerate(plan.children):
                await process_page_recursive(child_plan, parent_id=db_page.id, order=i, model=model)

        for i, page_plan in enumerate(pages_to_generate):
            await process_page_recursive(page_plan, parent_id=None, order=i, model=model)
        return saved_pages


wiki_service = WikiService()
