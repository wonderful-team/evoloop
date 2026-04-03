import json
import os
import shutil
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from langchain_core.messages import HumanMessage
from app.utils import render_template
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.domain.wiki.wiki_builder import WikiBuilder
from app.core.evocloud import evocloud_manager
from app.core.file.service import filter_code_files, walk_tree
from app.core.memory import MemoryContainer, MemoryConfig
from app.i18n.service import i18n
from app.models.wiki import WikiPage
from app.utils.file import normalize_path

logger = logging.getLogger(__name__)


# --- Pydantic models for structured LLM output ---
class ExtractedConcept(BaseModel):
    name: str = Field(description="Name of the concept")
    description: str = Field(description="Description of what it is and why it matters")


class ConceptExtractionResult(BaseModel):
    concepts: list[ExtractedConcept] = Field(default_factory=list)


class WikiService:
    """
    Service for Wiki page management and generation.
    Integrates with MemoryService to extract and store knowledge concepts.
    """

    def get_pages(self, project_id: int) -> list[WikiPage]:
        with Session(engine) as session:
            statement = select(WikiPage).where(WikiPage.project_id == project_id).order_by(WikiPage.order)
            results = session.exec(statement)
            return results.all()

    def get_page(self, page_id: int) -> WikiPage | None:
        with Session(engine) as session:
            return session.get(WikiPage, page_id)

    def get_projects_with_wiki(self, project_ids: list[int]) -> set[int]:
        """
        Efficiently check which projects have wiki pages.
        """
        if not project_ids:
            return set()
        with Session(engine) as session:
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
            # walk_tree handles standard directory exclusion (node_modules, .git, etc.)
            all_files_abs = list(walk_tree(root_path))

            # 2. Convert to relative and normalize
            all_files_rel = []
            for f in all_files_abs:
                rel = os.path.relpath(f, root_path)
                all_files_rel.append(normalize_path(rel))

            # 3. Apply code file filtering (extensions, specific exclusion lists)
            # Check exclusions that might not be in walk_tree default
            valid_files = filter_code_files(all_files_rel)

            # 4. Build Tree String
            return self._paths_to_tree_string(valid_files)

        except Exception as e:
            logger.error(f"Error generating file tree: {e}")
            return "(Error generating file tree)"

    def _paths_to_tree_string(self, paths: list[str]) -> str:
        """
        Converts a list of file paths into a visual tree string.
        Uses Jinja2 template for rendering.
        """
        from app.utils import render_template
        
        paths.sort()
        lines = []
        prev_parts = []
        truncated = False

        for path in paths:
            parts = path.split("/")  # paths are normalized
            # Determine common depth
            common_depth = 0
            for i in range(min(len(parts), len(prev_parts))):
                if parts[i] == prev_parts[i]:
                    common_depth += 1
                else:
                    break

            # Prepare data for new parts
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
            "wiki/file_tree.prompt.j2",
            lines=lines,
            truncated=truncated
        )

    def _read_file_safe(self, path: str, max_chars: int = 50000) -> str:
        """
        Reads a file safely with a character limit.
        """
        if not os.path.exists(path):
            return ""
        if os.path.isdir(path):
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
        llm,
    ) -> list[str]:
        """
        Extract knowledge concepts from a Wiki page and store them in Agent memory.
        Returns list of concept names that were stored.
        """
        # Check if feature is enabled
        if not getattr(settings, 'WIKI_EXTRACT_CONCEPTS', True):
            return []

        try:
            # Build extraction prompt
            builder = WikiBuilder()
            extraction_prompt = builder.build_concept_extraction_prompt(page_title, page_content)

            # Try structured output first
            try:
                structured_llm = llm.with_structured_output(ConceptExtractionResult)
                result = await structured_llm.ainvoke([HumanMessage(content=extraction_prompt)])
            except Exception:
                # Fallback to raw JSON extraction
                response = await llm.ainvoke([HumanMessage(content=extraction_prompt)])
                json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
                if json_match:
                    result_dict = json.loads(json_match.group(0))
                    result = ConceptExtractionResult(**result_dict)
                else:
                    result = ConceptExtractionResult(concepts=[])

            stored_names = []
            if result and result.concepts:
                container = MemoryContainer(MemoryConfig.from_settings())
                await container.initialize()
                try:
                    manager = container.memory_manager
                    for concept in result.concepts[:5]:  # Max 5 concepts per page
                        from app.core.memory.interfaces.long_term import Concept as MemConcept
                        mem_concept = MemConcept(concept.name, concept.description, project_id, [])
                        await manager.long_term.store_concept(mem_concept)
                        stored_names.append(concept.name)
                        logger.info(f"Wiki Concept Harvested: {concept.name}")
                finally:
                    await container.shutdown()

            return stored_names

        except Exception as e:
            logger.warning(f"Failed to extract concepts from wiki page '{page_title}': {e}")
            return []

    async def _validate_structure(
        self,
        structure_data: dict,
        project_context: str,
        llm,
    ) -> dict:
        """
        Validate Wiki structure completeness using LLM-based dynamic analysis.
        Returns updated structure with any missing pages added.
        """
        try:
            builder = WikiBuilder()
            validation_prompt = builder.build_validation_prompt(structure_data, project_context)
            response = await llm.ainvoke([HumanMessage(content=validation_prompt)])
            response_text = response.content

            # Extract JSON
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                logger.info("Structure validation: No JSON in response, assuming complete")
                return structure_data

            validation_result = json.loads(json_match.group(0))
            is_complete = validation_result.get("is_complete", True)
            gaps = validation_result.get("gaps", [])

            if is_complete or not gaps:
                logger.info("Structure validation: Structure is complete")
                return structure_data

            # Add missing pages
            logger.info(f"Structure validation: Found {len(gaps)} gaps, adding pages")
            pages = structure_data.get("pages", [])

            for gap in gaps:
                suggested_title = gap.get("suggested_title", gap.get("area", "Additional Page"))
                # Generate a slug from the title
                slug = suggested_title.lower().replace(" ", "-").replace("_", "-")
                slug = re.sub(r'[^a-z0-9-]', '', slug)[:50]

                new_page = {
                    "id": f"gap-{slug}",
                    "title": suggested_title,
                    "description": gap.get("reason", ""),
                    "relevant_files": [],
                    "importance": "medium",
                    "children": []
                }
                pages.append(new_page)
                logger.info(f"  -> Added page: {suggested_title}")

            structure_data["pages"] = pages
            return structure_data

        except Exception as e:
            logger.warning(f"Structure validation failed: {e}. Proceeding with original structure.")
            return structure_data

    async def generate_wiki(self, project_id: int, topic: str, llm, force_regenerate: bool = False):
        """
        Generates Wiki content using a 'Technical Writer' workflow (Structure -> Content).
        Phase 1: Determine Structure (Planner).
        Phase 2: Generate Page Content (Writer).
        """
        logger.info(f"Starting Wiki Generation for project {project_id}")

        # 0. Context Setup
        project_data = await evocloud_manager.get_project_by_id(project_id)
        if not project_data or not project_data.get('path'):
            logger.error(f"Project path not found for id {project_id}")
            return []

        project_path = project_data['path']
        logger.info(f"Using project path: {project_path}")

        # 1. Phase 1: Determine Structure
        logger.info("Phase 1: Determining Wiki Structure...")

        # Handle cleanup if force regenerating
        if force_regenerate:
            logger.info("Force regenerate: deleting existing wiki pages.")
            from sqlmodel import delete
            with Session(engine) as session:
                statement = delete(WikiPage).where(WikiPage.project_id == project_id)
                session.exec(statement)
                session.commit()
        file_tree = self._get_file_tree(project_path)
        readme_path = os.path.join(project_path, "README.md")
        readme_content = self._read_file_safe(readme_path)

        builder = WikiBuilder()
        structure_prompt = builder.build_structure_prompt(file_tree, readme_content)

        try:
            # Call LLM for structure
            structure_response = await llm.ainvoke([HumanMessage(content=structure_prompt)])
            response_text = structure_response.content

            # Extract JSON
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                structure_data = json.loads(json_match.group(0))
                # Validate structure
                if "pages" in structure_data and isinstance(structure_data["pages"], list):
                    pages_to_generate = structure_data["pages"]
                else:
                    raise ValueError("Invalid JSON structure: missing 'pages' list")
            else:
                raise ValueError("No JSON found in response")

        except Exception as e:
            logger.error(f"Failed to determine wiki structure: {e}. Falling back to default.")
            # Fallback structure
            pages_to_generate = [
                {"title": i18n.get("wiki.fallback.overview"), "id": "overview", "relevant_files": []},
                {"title": i18n.get("wiki.fallback.architecture"), "id": "architecture", "relevant_files": []},
                {"title": i18n.get("wiki.fallback.setup"), "id": "setup", "relevant_files": []}
            ]
            structure_data = {"pages": pages_to_generate}

        # 1.5 Phase 1.5: Validate Structure Completeness
        logger.info("Phase 1.5: Validating Wiki Structure...")
        project_context = f"Project path: {project_path}\nREADME preview: {readme_content[:500] if readme_content else 'No README'}"

        validated_structure = await self._validate_structure(
            structure_data=structure_data,
            project_context=project_context,
            llm=llm,
        )
        pages_to_generate = validated_structure.get("pages", pages_to_generate)

        logger.info(f"Planned {len(pages_to_generate)} pages: {[p.get('title') for p in pages_to_generate]}")

        saved_pages = []

        # 2. Phase 2: Generate Content (Recursive)
        async def process_page_recursive(plan, parent_id=None, order=0):
            page_title = plan.get("title", "Untitled")
            page_slug = plan.get("id", f"page-{order}")
            relevant_files_hint = plan.get("relevant_files", [])

            logger.info(f"Phase 2: Generating content for '{page_title}' (slug: {page_slug})")

            page_content = None

            # Check existence
            if not force_regenerate:
                with Session(engine) as session:
                    stmt = select(WikiPage).where(
                        WikiPage.project_id == project_id,
                        WikiPage.slug == page_slug
                    )
                    existing_page = session.exec(stmt).first()
                    if existing_page and existing_page.content:
                        logger.info(f"Skipping '{page_title}' - already exists.")
                        # Ensure hierarchy is up to date
                        if existing_page.parent_id != parent_id or existing_page.order != order:
                            existing_page.parent_id = parent_id
                            existing_page.order = order
                            session.add(existing_page)
                            session.commit()
                            session.refresh(existing_page)

                        saved_pages.append(existing_page)

                        # Recurse Children even if skipped
                        children = plan.get("children", [])
                        for i, child_plan in enumerate(children):
                            await process_page_recursive(child_plan, parent_id=existing_page.id, order=i)
                        return

            # Gather context
            files_to_read_content: Dict[str, str] = {}

            # Helper to expand directories
            from app.core.file.service import filter_code_files, walk_tree
            final_files_to_read = []

            for rel_path in relevant_files_hint:
                full_path = os.path.join(project_path, rel_path)
                if os.path.exists(full_path) and os.path.isdir(full_path):
                    # Expand directory
                    try:
                        # Get all files recursively
                        child_files = list(walk_tree(full_path))
                        # Convert to relative paths
                        child_rels = [os.path.relpath(f, project_path) for f in child_files]
                        # Filter code files
                        filtered_children = filter_code_files(child_rels)
                        # Limit to avoid explosion (e.g. max 10 files per directory hint)
                        final_files_to_read.extend(filtered_children[:10])
                    except Exception as e:
                        logger.warning(f"Failed to expand directory {rel_path}: {e}")
                else:
                    final_files_to_read.append(rel_path)

            # Remove duplicates while preserving order
            final_files_to_read = list(dict.fromkeys(final_files_to_read))

            for rel_path in final_files_to_read:
                full_path = os.path.join(project_path, rel_path)
                content = self._read_file_safe(full_path, max_chars=50000)
                if content:
                    files_to_read_content[rel_path] = content

            if not files_to_read_content and readme_content:
                files_to_read_content["README.md"] = readme_content

            # Build prompt using Jinja2 template
            try:
                files_data = []
                for rel_path, content in files_to_read_content.items():
                    files_data.append({"path": rel_path, "content": content})

                # Re-generate file tree for the prompt, potentially with only relevant files
                # Or use the full file_tree generated earlier if it's deemed more useful
                # For now, let's use the full file_tree
                content_prompt = render_template(
                    "wiki/wiki_context.prompt.j2",
                    page_title=page_title,
                    files=files_data,
                    tree=file_tree # Using the full file_tree from earlier
                )

            except Exception as e:
                logger.error(f"Failed to render Wiki context template for page '{page_title}': {e}")
                # Fallback to old prompt generation if template fails
                joined_context = "\n".join([f"--- FILE: {p} ---\n{c}\n" for p, c in files_to_read_content.items()])
                valid_paths = list(files_to_read_content.keys())
                builder = WikiBuilder()
                content_prompt = builder.build_content_prompt(page_title, joined_context, valid_paths)


            try:
                content_response = await llm.ainvoke([HumanMessage(content=content_prompt)])
                page_content = content_response.content
            except Exception as e:
                logger.error(f"Error generating page content: {e}")
                error_msg = i18n.get("wiki.error_generating_content", error=str(e))
                page_content = f"# {page_title}\n\n{error_msg}"

            # Save to DB
            with Session(engine) as session:
                stmt = select(WikiPage).where(
                    WikiPage.project_id == project_id,
                    WikiPage.slug == page_slug
                )
                existing_page_db = session.exec(stmt).first()

                if existing_page_db:
                    existing_page_db.content = page_content
                    existing_page_db.updated_at = datetime.utcnow()
                    existing_page_db.title = page_title
                    existing_page_db.order = order
                    existing_page_db.parent_id = parent_id
                    session.add(existing_page_db)
                    session.commit()
                    session.refresh(existing_page_db)
                    saved_page = existing_page_db
                else:
                    new_page = WikiPage(
                        project_id=project_id,
                        title=page_title,
                        slug=page_slug,
                        content=page_content,
                        order=order,
                        parent_id=parent_id
                    )
                    session.add(new_page)
                    session.commit()
                    session.refresh(new_page)
                    saved_page = new_page

            saved_pages.append(saved_page)

            # Phase 2.5: Extract and store knowledge concepts
            if page_content:
                extracted = await self._extract_and_store_concepts(
                    page_title=page_title,
                    page_content=page_content,
                    project_id=project_id,
                    llm=llm,
                )
                if extracted:
                    logger.info(f"Extracted {len(extracted)} concepts from '{page_title}'")

            # Recurse Children
            children = plan.get("children", [])
            for i, child_plan in enumerate(children):
                await process_page_recursive(child_plan, parent_id=saved_page.id, order=i)

        # Kickoff recursion
        for i, page_plan in enumerate(pages_to_generate):
            await process_page_recursive(page_plan, parent_id=None, order=i)

        return saved_pages


wiki_service = WikiService()
