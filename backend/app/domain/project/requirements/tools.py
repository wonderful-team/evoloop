"""
Agent tools for requirement analysis.
"""

import json
import logging
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableConfig

from app.core.file.document_reader import document_reader_service
from app.core.tools import evoloop_tool

from app.utils.id import gen_uuid
from app.utils.time import utcnow

from .models import ProjectRequirementAnalysis, ProjectRequirementDocument
from .prompts import render_analysis_prompt
from .service import breakdown_requirements_to_tasks

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@evoloop_tool
async def analyze_project_requirement_document(
    document_id: str,
    focus_areas: list[str] | None = None,
    config: RunnableConfig | None = None
) -> str:
    """
    Analyze a project requirement document and extract structured requirements.

    Use Cases:
    - After user uploads a requirement document, automatically extract functional requirements, user stories, technical suggestions, etc.
    - Support for Word/Excel/PDF/Markdown/Text documents

    Args:
        document_id: The ID of the requirement document to analyze
        focus_areas: Optional focus areas for the analysis (e.g., ["performance", "security", "UX"])

    Returns:
        JSON string containing structured analysis results
    """
    from app.infrastructure.database.sql.database import session_scope

    async with session_scope() as session:
        # Get document
        doc = await session.get(ProjectRequirementDocument, document_id)
        if not doc:
            return json.dumps({"error": f"Document {document_id} not found"})

        # Read file content (if not cached)
        if not doc.raw_content:
            try:
                content = await document_reader_service.read_document(doc.file_path)
                doc.raw_content = content
            except Exception as e:
                return json.dumps({"error": f"Failed to read document: {e}"})

        # Call LLM analysis using InternalLLMService
        prompt = render_analysis_prompt(
            document_content=doc.raw_content[:15000],
            focus_areas=focus_areas,
            language="Chinese"
        )

        from app.core.llm import InternalLLMService
        response = await InternalLLMService.invoke(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "请分析上述需求文档，以JSON格式输出结构化分析结果。"}
            ],
            purpose="task_analysis",
        )

        # Parse and save
        try:
            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content

            analysis_result = json.loads(json_str)

            analysis = ProjectRequirementAnalysis(
                id=gen_uuid(),
                document_id=document_id,
                project_id=doc.project_id,
                analysis_data=analysis_result,
                status="pending_confirmation"
            )
            session.add(analysis)

            doc.status = "analyzed"

            return json.dumps({
                "success": True,
                "analysis_id": analysis.id,
                "project_id": doc.project_id,
                "result": analysis_result,
                "message": "需求分析完成，等待用户确认"
            }, ensure_ascii=False)

        except json.JSONDecodeError as e:
            return json.dumps({
                "error": f"Failed to parse LLM response: {e}",
                "raw_response": content
            })


@evoloop_tool
async def confirm_project_requirement_analysis(
    analysis_id: str,
    modifications: dict | None = None,
    auto_breakdown: bool = True,
    breakdown_strategy: str = "module_based",
    config: RunnableConfig | None = None
) -> str:
    """
    Confirm requirement analysis results and trigger automatic task breakdown and EvoCloud sync.

    Use Cases:
    - User reviews and confirms the AI-generated analysis
    - User modifies the analysis before confirmation

    IMPORTANT: This tool automatically:
    1. Saves the confirmed analysis (with any user modifications)
    2. Breaks down requirements into tasks via LLM
    3. Triggers background Celery task to sync tasks to EvoCloud
    """
    from app.infrastructure.database.sql.database import session_scope

    async with session_scope() as session:
        analysis = await session.get(ProjectRequirementAnalysis, analysis_id)
        if not analysis:
            return json.dumps({"error": "Analysis not found"})

        # Apply modifications
        if modifications:
            analysis.analysis_data.update(modifications)
            analysis.user_edited = True

        analysis.status = "confirmed"
        analysis.confirmed_at = utcnow()

        result = {
            "success": True,
            "analysis_id": analysis_id,
            "status": "confirmed"
        }

        # Automatic task breakdown
        if auto_breakdown:
            breakdown_result = await breakdown_requirements_to_tasks(
                analysis=analysis,
                strategy=breakdown_strategy
            )

            result["breakdown"] = {
                "tasks_created": len(breakdown_result["tasks"]),
                "tasks": breakdown_result["tasks"]
            }

            # Trigger background sync to EvoCloud
            from app.domain.project.sync_tasks import sync_tasks_to_evocloud_task

            task_ids = [t["id"] for t in breakdown_result["tasks"]]
            sync_tasks_to_evocloud_task.delay(analysis_id, task_ids)

            result["sync"] = {
                "status": "queued",
                "message": f"{len(task_ids)} tasks queued for EvoCloud sync"
            }

        return json.dumps(result, ensure_ascii=False)
