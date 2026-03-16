"""
Orchestration & Control Tools - Phase 5 Architectural Consolidation
Consolidates engine-level control tools (Routing, State, Parallelism) into a unified module.
"""

import json
import logging
import re
from typing import Any, Optional

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from app.constants import RoutingTarget
from app.core.tools import evoloop_tool
from app.infrastructure.llm.factory import LLMFactory
from app.i18n.service import i18n
from app.utils.text import extract_json_from_markdown

logger = logging.getLogger(__name__)


# ===== 1. State Management Tools (v1 Evolution) =====

@evoloop_tool(is_state_mutating=True)
def update_blackboard(key: str, value: Any, _config: RunnableConfig) -> str:
    """
    Updates the agent's dynamic state center (blackboard) with a key-value pair.
    Useful for passing information between nodes or controlling autonomous flow.

    Args:
        key: The variable name to set (e.g., "complexity", "status").
        value: The value to assign (can be string, number, boolean, etc.).
    """
    return f"State updated: {key}={value}"


@evoloop_tool(is_state_mutating=True)
def manage_session_metadata(key: str, value: Any, _config: RunnableConfig) -> str:
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
    return f"Session metadata set: {key}={value}"


# ===== 2. Routing Tools (v2 Evolution) =====

@evoloop_tool(is_state_mutating=True)
def route_to(
    target: RoutingTarget,
    reason: str,
    context: dict[str, Any] | None = None,
    authorized_tools: list[str] | None = None,
) -> str:
    """
    Hand off the current task to a specialist node.
    This is the primary way the Supervisor moves the workflow forward.

    Available targets:
    - "worker": Universal executor for coding, file operations, and system control.
    - "deep_researcher": Web search and information gathering.
    - "documenter": Generate documentation, wiki, or README.
    - "chat": Ask questions or provide a direct response to the user.
    - "finish": Task completion or question fully answered.

    Args:
        target: The target specialist node.
        reason: Why this handoff is occurring.
        context: Structured guidance or attention focus for the specialist.
        authorized_tools: Restricted set of tools if specific constraints are needed.
    """
    context_str = json.dumps(context, ensure_ascii=False) if context else "{}"
    target_val = target.value if hasattr(target, "value") else target
    return f"[ROUTE_SIGNAL] → {target_val}: {reason} | Context: {context_str}"


# ===== 3. Coordination & Planning Tools (v3/4 Evolution) =====


@evoloop_tool()
async def decompose_task(
    task_description: str,
    context: str = "",
    max_parallel: int = 5,
    requires_aggregation: bool = True
) -> dict[str, Any]:
    """
    Analyzes and breaks down a complex task into multiple parallel sub-tasks.
    
    Returns a SpawnPlan that triggers the parallel execution engine.
    """
    llm = LLMFactory.create_llm(temperature=0.3)

    prompt = f"""你是一个任务规划专家。请将以下任务分解为可并行执行的子任务。

原始任务: {task_description}
上下文: {context}
最大并行度: {max_parallel}

输出规格:
1. 识别独立实体或可并行化路径。
2. 为每个子任务配合明确的 intent 和所需工具建议。
3. 产出严格 JSON。

JSON Format:
{{
    "can_parallelize": true,
    "strategy": "parallel",
    "reasoning": "...",
    "subtasks": [
        {{
            "id": "task_1",
            "intent": "...",
            "tools": ["tool_1"],
            "estimated_complexity": "low"
        }}
    ],
    "aggregation_strategy": "merge" | "concatenate" | "analyze"
}}"""

    try:
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        json_content = extract_json_from_markdown(response.content)
        plan = json.loads(json_content)

        plan["_routing_signal"] = "spawn_subtasks"
        plan["_requires_aggregation"] = requires_aggregation
        plan["parent_task"] = task_description

        return {
            "status": "success",
            "_routing_target": "spawn_subtasks",
            "_spawn_plan": plan
        }
    except Exception as e:
        logger.error(f"[decompose_task] Failed: {e}")
        return {"status": "error", "error": str(e)}


@evoloop_tool()
async def spawn_agents(
    mission_plan: dict[str, Any],
    reasoning: str = "",
    requires_aggregation: bool = True
) -> dict[str, Any]:
    """
    Directly spawns multiple sub-agents based on a provided mission plan.
    High-level coordination for models that prefer explicitly managing parallelism.
    """
    logger.info(f"[spawn_agents] 🚀 Spawning {len(mission_plan.get('subtasks', []))} agents: {reasoning}")
    
    plan = {
        "subtasks": mission_plan.get("subtasks", []),
        "aggregation_strategy": mission_plan.get("aggregation_strategy", "merge"),
        "_requires_aggregation": requires_aggregation,
        "parent_task": reasoning or "Autonomous Mission",
    }

    return {
        "status": "success",
        "_routing_target": "spawn_subtasks",
        "_spawn_plan": plan
    }


@evoloop_tool()
async def aggregate_results(
    aggregation_strategy: str,
    results: list[dict],
    original_task: str = ""
) -> dict[str, Any]:
    """
    Aggregates outcomes from multiple parallel sub-tasks using the specified strategy.
    """
    if not results:
        return {"status": "success", "aggregated": "N/A"}

    if aggregation_strategy == "concatenate":
        return {"status": "success", "aggregated": "\n\n---\n\n".join([str(r.get("result", r)) for r in results])}

    llm = LLMFactory.create_llm(temperature=0.3)
    prompt = f"Original Task: {original_task}\nStrategy: {aggregation_strategy}\nResults: {json.dumps(results, ensure_ascii=False)}\n\nAggregate these findings into a concise summary."
    
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    return {"status": "success", "aggregated": response.content}
