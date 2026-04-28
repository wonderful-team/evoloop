"""
Task planning tool — decomposes complex tasks into parallel sub-tasks.
"""

import json
import logging

from app.core.engine.state.blackboard import SpawnPlan
from app.core.engine.tools.orchestration.schemas import DecomposeTaskResult
from app.core.tools import evoloop_tool
from app.utils.text import extract_json_from_markdown

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_hidden=True,  # Internal task planning, not user-facing
    name_map={"zh": "分解任务", "en": "Decompose Task"}
)
async def decompose_task(
    task_description: str,
    context: str = "",
    max_parallel: int = 5,
    requires_aggregation: bool = True
) -> DecomposeTaskResult:
    """
    Analyzes and breaks down a complex task into multiple parallel sub-tasks.
    
    Returns a SpawnPlan that triggers the parallel execution engine.
    """
    from app.utils import render_template
    prompt = render_template(
        "core/engine/tools/orchestration_decompose.prompt.j2",
        task_description=task_description,
        context=f"Context: {context}\nMax Parallelism: {max_parallel}"
    )

    try:
        from app.core.llm import InternalLLMService
        from app.infrastructure.config.service import SystemConfigService
        model_name = SystemConfigService.get_value("LLM_MODEL")
        response = await InternalLLMService.invoke(
            messages=[{"role": "user", "content": prompt}],
            purpose="task_decomposition",
            temperature=0.3,
            model_name=model_name,
        )
        content = response.content
        json_content = extract_json_from_markdown(content)
        subtasks = json.loads(json_content)

        # LLM should return an array of task objects per the prompt
        if not isinstance(subtasks, list):
            return DecomposeTaskResult(
                status="error",
                error=f"Expected JSON array of tasks, got {type(subtasks).__name__}. Please ensure the prompt requests an array format."
            )

        plan = SpawnPlan(
            subtasks=subtasks,
            routing_signal="spawn_subtasks",
            requires_aggregation=requires_aggregation,
            parent_task=task_description
        )

        return DecomposeTaskResult(
            status="success",
            routing_target="spawn_subtasks",
            spawn_plan=plan
        )
    except Exception as e:
        logger.error(f"[decompose_task] Failed: {e}")
        return DecomposeTaskResult(status="error", error=str(e))
