"""
Parallelism tools — spawn agents and aggregate results.
"""

import json
import logging
from typing import Any

from app.core.engine.state.blackboard import SpawnPlan
from app.core.engine.tools.orchestration.schemas import AggregateResult, SpawnAgentsResult
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_hidden=True,  # Internal parallel coordination, not user-facing
    name_map={"zh": "生成代理", "en": "Spawn Agents"}
)
async def spawn_agents(
    mission_plan: SpawnPlan | dict[str, Any],
    reasoning: str = "",
    requires_aggregation: bool = True
) -> SpawnAgentsResult:
    """
    Directly spawns multiple sub-agents based on a provided mission plan.
    High-level coordination for models that prefer explicitly managing parallelism.
    """
    if isinstance(mission_plan, dict):
        # Normalize raw dict input before Pydantic validation
        raw_subtasks = mission_plan.get("subtasks") or []
        for idx, subtask in enumerate(raw_subtasks):
            if isinstance(subtask, dict):
                if "subtask_id" in subtask and "id" not in subtask:
                    subtask["id"] = subtask.pop("subtask_id")
                if not subtask.get("id") or subtask.get("id") == "unknown":
                    from app.utils.id import gen_uuid
                    subtask["id"] = f"agent-{gen_uuid()[:8]}-{idx}"
        mission_plan = SpawnPlan.model_validate(mission_plan)

    logger.info(f"[spawn_agents] 🚀 Spawning {len(mission_plan.subtasks or [])} agents: {reasoning}")

    subtasks = list(mission_plan.subtasks or [])

    # Enforce unique IDs for spawned agents
    for idx, subtask in enumerate(subtasks):
        if not subtask.id or subtask.id == "unknown":
            from app.utils.id import gen_uuid
            subtasks[idx] = subtask.model_copy(update={"id": f"agent-{gen_uuid()[:8]}-{idx}"})

    plan = SpawnPlan(
        subtasks=subtasks,
        aggregation_strategy=mission_plan.aggregation_strategy or "merge",
        requires_aggregation=requires_aggregation,
        parent_task=reasoning or "Autonomous Mission",
    )

    return SpawnAgentsResult(
        status="success",
        routing_target="spawn_subtasks",
        spawn_plan=plan
    )


@evoloop_tool(
    is_hidden=True,  # Internal result aggregation, not user-facing
    name_map={"zh": "聚合结果", "en": "Aggregate Results"}
)
async def aggregate_results(
    aggregation_strategy: str,
    results: list[dict],
    original_task: str = ""
) -> AggregateResult:
    """
    Aggregates outcomes from multiple parallel sub-tasks using the specified strategy.
    """
    if not results:
        return AggregateResult(status="success", aggregated="N/A")

    if aggregation_strategy == "concatenate":
        return {"status": "success", "aggregated": "\n\n---\n\n".join([str(r.get("result", r)) for r in results])}

    from app.core.llm import InternalLLMService
    from app.utils import render_template
    prompt = render_template(
        "core/engine/tools/orchestration_aggregate.prompt.j2",
        original_task=original_task,
        aggregation_strategy=aggregation_strategy,
        results_json=json.dumps(results, ensure_ascii=False)
    )

    response = await InternalLLMService.invoke(
        messages=[{"role": "user", "content": prompt}],
        purpose="result_aggregation",
        temperature=0.3,
    )
    content = response.content if hasattr(response, 'content') else str(response)
    return AggregateResult(status="success", aggregated=content)
