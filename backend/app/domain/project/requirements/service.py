"""
Internal services for requirement analysis.
"""

import json
import logging
from typing import TYPE_CHECKING


from app.utils.id import gen_uuid

from .models import ProjectRequirementTask
from .prompts import render_breakdown_prompt

if TYPE_CHECKING:
    from .models import ProjectRequirementAnalysis

logger = logging.getLogger(__name__)


async def breakdown_requirements_to_tasks(
    analysis: "ProjectRequirementAnalysis",
    strategy: str = "module_based"
) -> dict:
    """
    Internal service: Break down requirement analysis into tasks.
    Called by confirm_project_requirement_analysis tool.
    """
    from app.infrastructure.database.sql.database import session_scope

    analysis_data = analysis.analysis_data

    # Prepare prompt using Jinja2 template
    prompt = render_breakdown_prompt(
        title=analysis_data.get("title", "Untitled"),
        summary=analysis_data.get("summary", ""),
        functional_requirements=analysis_data.get("functional_requirements", []),
        user_stories=analysis_data.get("user_stories", []),
        technical_suggestions=analysis_data.get("technical_suggestions", []),
        strategy=strategy,
        language="Chinese"
    )

    # Call LLM using InternalLLMService
    from app.core.llm import InternalLLMService
    response = await InternalLLMService.invoke(
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": "请将需求拆解为任务，以JSON格式输出。"}
        ],
        purpose="task_decomposition",
    )

    # Parse result
    content = response.content
    if "```json" in content:
        json_str = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        json_str = content.split("```")[1].split("```")[0].strip()
    else:
        json_str = content

    breakdown_result = json.loads(json_str)
    tasks_data = breakdown_result.get("tasks", [])

    # Save to database
    async with session_scope() as session:
        created_tasks = []
        for idx, task_data in enumerate(tasks_data):
            task = ProjectRequirementTask(
                id=gen_uuid(),
                analysis_id=analysis.id,
                project_id=analysis.project_id,
                task_data=task_data,
                sync_status="pending"
            )
            session.add(task)
            created_tasks.append({
                "id": task.id,
                "title": task_data.get("title"),
                "sync_status": "pending"
            })

    return {"tasks": created_tasks}
