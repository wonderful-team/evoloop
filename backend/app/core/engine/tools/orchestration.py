"""
Orchestration & Control Tools - Phase 5 Architectural Consolidation
Consolidates engine-level control tools (Routing, State, Parallelism) into a unified module.
"""

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.routers import RoutingTarget
from app.core.engine.signals import RoutingContext
from app.core.engine.state.blackboard import SpawnPlan
from app.core.tools import evoloop_tool
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.text import extract_json_from_markdown

logger = logging.getLogger(__name__)


class ToolResult(DynamicBaseModel):
    status: str
    message: str
    _signal: str | None = None
    data: dict | None = None


class DecomposeTaskResult(DynamicBaseModel):
    status: str
    error: str | None = None
    routing_target: str | None = None
    spawn_plan: SpawnPlan | None = None


class SpawnAgentsResult(DynamicBaseModel):
    status: str
    routing_target: str | None = None
    spawn_plan: SpawnPlan | None = None


class AggregateResult(DynamicBaseModel):
    status: str
    aggregated: Any


# ===== 1. State Management Tools (v1 Evolution) =====

@evoloop_tool(
    is_state_mutating=True,
    is_hidden=True,  # Internal state management, not user-facing
    name_map={"zh": "更新黑板", "en": "Update Blackboard"}
)
def update_blackboard(key: str, value: Any, _config: RunnableConfig) -> ToolResult:
    """
    [DEPRECATED] Updates the agent's dynamic state center (blackboard).
    
    NOTE: In Phase 5+, you can update the blackboard more efficiently by 
    simply including '[BLACKBOARD: key=value]' in your text response/thought.
    This saves an LLM turn.

    Args:
        key: The variable name to set (e.g., "complexity", "status").
        value: The value to assign (can be string, number, boolean, etc.).
    """
    return ToolResult(
        status="success",
        message=f"State field '{key}' updated successfully. (Note: Inferred update via '[BLACKBOARD: {key}={value}]' is preferred)",
        _signal="update_blackboard",
        data={"key": key, "value": value}
    )


@evoloop_tool(
    is_state_mutating=True,
    is_hidden=True,  # Internal state management, not user-facing
    name_map={"zh": "管理会话元数据", "en": "Manage Session Metadata"}
)
def manage_session_metadata(key: str, value: Any, _config: RunnableConfig) -> ToolResult:
    """
    Updates session-level metadata to guide the agent's behavior and context resolution.
    
    Common keys:
    - 'current_ecosystem': Set to 'android', 'macos', or 'web' based on telemetry.
    - 'user_persona': Describe the user style or specific domain expertise needed.
    - 'priority': 'low', 'normal', 'high', 'emergency'.
    
    Args:
        key: The metadata key to set.
        value: The value to assign.
    """
    return ToolResult(
        status="success",
        message=f"Session metadata '{key}' updated successfully.",
        _signal="update_session_metadata",
        data={"key": key, "value": value}
    )


# ===== 2. Routing Tools (v2 Evolution) =====

@evoloop_tool(
    is_state_mutating=True,
    is_hidden=True,  # Internal routing signal, not user-facing
    name_map={"zh": "路由到", "en": "Route To"}
)
def route_to(
    target: RoutingTarget,
    reason: str,
    context: RoutingContext | None = None,
    authorized_tools: list[str] | None = None,
    skill_id: int | None = None,
    # 新增：支持多技能工作流
    skill_ids: list[int] | None = None,
    workflow_mode: str = "single",
) -> str:
    """
    [MANDATORY] Hand off the current task to a specialist node.

    ⚠️ CRITICAL: This tool MUST be called in EVERY Supervisor response.
    Outputting plain text without calling route_to will cause system failure.

    Available targets:
    - "worker": Universal executor for coding, file operations, and system control.
    - "deep_researcher": Web search and information gathering.
    - "documenter": Generate documentation, wiki, or README.
    - "chat": Ask questions or provide a direct response to the user.
    - "finish": Task completion or question fully answered.

    Args:
        target: The target specialist node. REQUIRED.
        reason: Why this handoff is occurring. REQUIRED.
        context: Structured guidance or attention focus for the specialist.
        authorized_tools: Restricted set of tools if specific constraints are needed.
                          The Supervisor should select appropriate tools from the
                          Worker Baseline Capability Pool defined in agent_main.yaml.
                          For deep_researcher: ["search_web", "browser_control", ...]
                          For documenter: ["read_file", "write_file", "list_directory", ...]
        skill_id: (Legacy) Single skill ID for backward compatibility.
        skill_ids: List of skill IDs for multi-step workflows (executed in order).
        workflow_mode: "single" for one skill, "sequential" for step-by-step execution.
    """
    target_val = target.value if hasattr(target, "value") else target

    ctx = context or RoutingContext()
    context_dict = ctx.model_dump()
    if authorized_tools:
        context_dict["authorized_tools"] = authorized_tools

    # 处理多技能工作流参数
    if skill_ids:
        context_dict["skill_ids"] = skill_ids
        context_dict["workflow_mode"] = workflow_mode
    elif skill_id:
        context_dict["skill_id"] = skill_id
        context_dict["workflow_mode"] = "single"

    context_str = json.dumps(context_dict, ensure_ascii=False)
    skill_info = f" | Skill ID: {skill_id}" if skill_id else ""
    if skill_ids:
        skill_info = f" | Skill IDs: {skill_ids}"
    tool_info = f" | Tools: {authorized_tools}" if authorized_tools else ""

    return f"ROUTE_SIGNAL|{target_val}|{reason}|{context_str}{skill_info}{tool_info}"


# ===== 3. Coordination & Planning Tools (v3/4 Evolution) =====


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
    # 2. Call LLM
    from app.utils import render_template
    prompt = render_template(
        "tool/orchestration_decompose.prompt.j2",
        task_description=task_description,
        context=f"Context: {context}\nMax Parallelism: {max_parallel}"
    )

    try:
        from app.core.llm import InternalLLMService
        response = await InternalLLMService.invoke(
            messages=[{"role": "user", "content": prompt}],
            purpose="task_decomposition",
            temperature=0.3,
        )
        content = response.content if hasattr(response, 'content') else str(response)
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
        "tool/orchestration_aggregate.prompt.j2",
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
