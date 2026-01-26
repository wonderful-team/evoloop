import logging
import os
from typing import List, Optional
from sqlmodel import Session, select
from datetime import datetime

from app.core.db import engine
from app.models.wiki import WikiPage, WikiPageCreate
from app.i18n.service import i18n

logger = logging.getLogger(__name__)

class WikiService:
    def get_pages(self, project_id: int) -> List[WikiPage]:
        with Session(engine) as session:
            statement = select(WikiPage).where(WikiPage.project_id == project_id).order_by(WikiPage.order)
            results = session.exec(statement)
            return results.all()

    def get_page(self, page_id: int) -> Optional[WikiPage]:
        with Session(engine) as session:
            return session.get(WikiPage, page_id)

    def get_projects_with_wiki(self, project_ids: List[int]) -> set[int]:
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
            from app.utils.file import walk_tree, filter_code_files, normalize_path
            
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

    def _paths_to_tree_string(self, paths: List[str]) -> str:
        """
        Converts a list of file paths into a visual tree string.
        """
        paths.sort()
        tree_lines = []
        prev_parts = []
        
        for path in paths:
            parts = path.split("/") # paths are normalized
            # Determine common depth
            common_depth = 0
            for i in range(min(len(parts), len(prev_parts))):
                if parts[i] == prev_parts[i]:
                    common_depth += 1
                else:
                    break
            
            # Print new parts
            for i in range(common_depth, len(parts)):
                indent = "  " * i
                name = parts[i]
                if i < len(parts) - 1:
                    # Directory
                    tree_lines.append(f"{indent}{name}/")
                else:
                    # File
                    tree_lines.append(f"{indent}{name}")
            
            prev_parts = parts
            
            if len(tree_lines) > 5000:
                tree_lines.append("... (truncated)")
                break
                
        return "\n".join(tree_lines)

    def _read_file_safe(self, path: str, max_chars: int = 50000) -> str:
        """
        Reads a file safely with a character limit.
        """
        if not os.path.exists(path):
            return ""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read(max_chars)
        except Exception as e:
            logger.warning(f"Failed to read file {path}: {e}")
            return ""

    async def generate_wiki(self, project_id: int, topic: str, llm, force_regenerate: bool = False):
        """
        Generates Wiki content using a 'Technical Writer' workflow (Structure -> Content).
        Phase 1: Determine Structure (Planner).
        Phase 2: Generate Page Content (Writer).
        """
        from app.domain.project.service import project_context_manager
        from app.core.prompts.wiki_builder import WikiBuilder
        from langchain_core.messages import SystemMessage, HumanMessage
        import json
        import re

        logger.info(f"Starting Wiki Generation for project {project_id}")

        # 0. Context Setup
        project_data = await project_context_manager.get_project_by_id(project_id)
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

        structure_prompt = WikiBuilder.build_structure_prompt(file_tree, readme_content)
        
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
                {"title": i18n.get("prompts.wiki.fallback.overview"), "id": "overview", "relevant_files": []},
                {"title": i18n.get("prompts.wiki.fallback.architecture"), "id": "architecture", "relevant_files": []},
                {"title": i18n.get("prompts.wiki.fallback.setup"), "id": "setup", "relevant_files": []}
            ]

        logger.info(f"Planned {len(pages_to_generate)} pages: {[p.get('title') for p in pages_to_generate]}")

        saved_pages = []

        # 2. Phase 2: Generate Content
        for i, page_plan in enumerate(pages_to_generate):
            page_title = page_plan.get("title", f"Page {i}")
            page_slug = page_plan.get("id", f"page-{i}")
            relevant_files_hint = page_plan.get("relevant_files", [])
            
            logger.info(f"Phase 2: Generating content for '{page_title}' (slug: {page_slug})")

            # Check existence - if page exists (e.g. from previous run without force, or partial run), skip it.
            # Since we cleared DB on force_regenerate, this only safeguards normal generation or partial restarts.
            if not force_regenerate:
                with Session(engine) as session:
                    stmt = select(WikiPage).where(
                        WikiPage.project_id == project_id,
                        WikiPage.slug == page_slug
                    )
                    existing = session.exec(stmt).first()
                    if existing and existing.content:
                        logger.info(f"Skipping '{page_title}' - already exists.")
                        saved_pages.append(existing)
                        continue

            # Gather context from relevant files
            context_buffer = []
            valid_paths = []
            
            # If no files suggested, try to find some intuitively (simplified)
            # In a real impl, we might do a vector search here. 
            # For now, we rely on the planner's suggestion.
            
            for rel_path in relevant_files_hint:
                full_path = os.path.join(project_path, rel_path)
                content = self._read_file_safe(full_path, max_chars=50000)
                if content:
                    context_buffer.append(f"--- FILE: {rel_path} ---\n{content}\n")
                    valid_paths.append(rel_path)
            
            # Usage of README as fallback context if buffer is empty
            if not context_buffer:
                context_buffer.append(f"--- FILE: README.md ---\n{readme_content}\n")
                valid_paths.append("README.md")

            joined_context = "\n".join(context_buffer)

            # Build Prompt
            content_prompt = WikiBuilder.build_content_prompt(page_title, joined_context, valid_paths)
            
            # Generate
            try:
                content_response = await llm.ainvoke([HumanMessage(content=content_prompt)])
                page_content = content_response.content
            except Exception as e:
                logger.error(f"Error generating page content: {e}")
                error_msg = i18n.get("prompts.wiki.error_generating_content", error=str(e))
                page_content = f"# {page_title}\n\n{error_msg}"

            # Save to DB
            with Session(engine) as session:
                stmt = select(WikiPage).where(
                    WikiPage.project_id == project_id,
                    WikiPage.slug == page_slug
                )
                existing_page = session.exec(stmt).first()
                
                if existing_page:
                    existing_page.content = page_content
                    existing_page.updated_at = datetime.utcnow()
                    existing_page.title = page_title
                    existing_page.order = i
                    session.add(existing_page)
                    session.commit()
                    session.refresh(existing_page)
                    saved_pages.append(existing_page)
                else:
                    new_page = WikiPage(
                        project_id=project_id,
                        title=page_title,
                        slug=page_slug,
                        content=page_content,
                        order=i
                    )
                    session.add(new_page)
                    session.commit()
                    session.refresh(new_page)
                    saved_pages.append(new_page)
        
        return saved_pages

wiki_service = WikiService()
