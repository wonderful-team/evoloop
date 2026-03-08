"""
Dynamic Task Planning Tools - Phase 1 Implementation

Provides LLM-driven task decomposition for parallel execution.
"""
import json
import logging
import re
from typing import Any

from app.core.tools import evoloop_tool
from app.infrastructure.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


def _extract_json_from_markdown(content: str) -> str:
    """Extract JSON from markdown code blocks or return raw content."""
    # Try to extract from ```json ... ``` or ``` ... ``` blocks
    patterns = [
        r'```json\s*(.*?)\s*```',  # ```json ... ```
        r'```\s*(.*?)\s*```',       # ``` ... ```
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
    return content.strip()


@evoloop_tool()
async def decompose_task(
    task_description: str,
    context: str = "",
    max_parallel: int = 5,
    requires_aggregation: bool = True
) -> dict[str, Any]:
    """
    将复杂任务分解为可并行执行的子任务。

    用于以下场景：
    - 批量处理（如采集多个商品、分析多个文件）
    - 多步骤复杂任务（需要条件分支或错误恢复）
    - 需要并行执行以提升效率的场景

    Args:
        task_description: 用户原始任务描述
        context: 额外上下文信息
        max_parallel: 最大并行度（默认5）
        requires_aggregation: 是否需要收集所有子任务结果后汇总

    Returns:
        包含分解结果的 dict，会被 AgentEngine 识别为动态路由信号
    """
    llm = LLMFactory.create_llm(temperature=0.3)

    prompt = f"""你是一个任务规划专家。请将以下任务分解为可并行执行的子任务。

原始任务: {task_description}
上下文: {context}
最大并行度: {max_parallel}

请分析任务是否可以并行化：

1. 如果任务是"采集10个商品详情"，应该分解为10个并行的子任务
2. 如果任务是"部署应用到K8s"，应该分解为顺序步骤（build → test → deploy）
3. 如果任务涉及多个独立实体（文件、URL、ID），为每个实体创建子任务

输出严格的JSON格式：
{{
    "can_parallelize": true/false,
    "strategy": "parallel" | "sequential" | "mixed",
    "reasoning": "为什么这样分解",
    "suggested_skill": "如果这是一个标准化任务，建议尝试使用的技能名称（如'采集闲鱼商品'），Worker会优先search_skills查找",
    "subtasks": [
        {{
            "id": "task_1",
            "intent": "子任务的具体目标",
            "tools": ["tool_name_1", "tool_name_2"],
            "skill_hint": "此子任务可能使用的已学习技能名称，Worker应优先尝试run_macro",
            "estimated_complexity": "low" | "medium" | "high",
            "depends_on": [],
            "context": {{
                "target": "具体目标（如商品ID、文件路径）",
                "parameters": {{}}
            }}
        }}
    ],
    "aggregation_strategy": "merge" | "concatenate" | "analyze" | "none"
}}

聚合策略说明：
- merge: 合并子任务结果（如合并多个商品数据到一个文件）
- concatenate: 简单拼接结果
- analyze: 对子任务结果进行进一步分析
- none: 不需要聚合，各自独立

只输出JSON，不要其他文字。"""

    try:
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        # Extract JSON from markdown code blocks if present
        json_content = _extract_json_from_markdown(response.content)
        plan = json.loads(json_content)

        # 验证结构
        if "subtasks" not in plan or not isinstance(plan["subtasks"], list):
            raise ValueError("Invalid plan structure: missing subtasks")

        # 添加元数据
        plan["_routing_signal"] = "spawn_subtasks"
        plan["_requires_aggregation"] = requires_aggregation
        plan["parent_task"] = task_description

        logger.info(f"[decompose_task] Generated plan with {len(plan['subtasks'])} subtasks, "
                   f"strategy={plan.get('strategy', 'unknown')}")

        return {
            "status": "success",
            "plan": plan,
            "subtask_count": len(plan["subtasks"]),
            "_routing_target": "spawn_subtasks",  # AgentEngine 会识别这个信号
            "_spawn_plan": plan
        }

    except json.JSONDecodeError as e:
        logger.error(f"[decompose_task] Failed to parse LLM response: {e}")
        return {
            "status": "error",
            "error": f"Failed to parse plan: {e}",
            "raw_response": response.content if 'response' in locals() else None
        }
    except Exception as e:
        logger.error(f"[decompose_task] Unexpected error: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@evoloop_tool()
async def aggregate_results(
    aggregation_strategy: str,
    results: list[dict],
    original_task: str = ""
) -> dict[str, Any]:
    """
    聚合多个子任务的结果。

    Args:
        aggregation_strategy: merge | concatenate | analyze | summarize
        results: 子任务结果列表
        original_task: 原始任务描述（用于上下文）

    Returns:
        聚合后的结果
    """
    if not results:
        return {"status": "success", "aggregated": "No subtask results to aggregate"}

    # 简单策略直接处理
    if aggregation_strategy == "concatenate":
        return {
            "status": "success",
            "aggregated": "\n\n---\n\n".join([str(r.get("result", r)) for r in results])
        }

    if aggregation_strategy == "merge" and all(isinstance(r, dict) for r in results):
        merged = {}
        for r in results:
            merged.update(r)
        return {"status": "success", "aggregated": merged}

    # 复杂策略使用 LLM
    llm = LLMFactory.create_llm(temperature=0.3)

    prompt = f"""请聚合以下子任务结果。

原始任务: {original_task}
聚合策略: {aggregation_strategy}

子任务结果:
{json.dumps(results, indent=2, ensure_ascii=False)}

请根据聚合策略生成统一的最终结果。"""

    response = await llm.ainvoke([{"role": "user", "content": prompt}])

    return {
        "status": "success",
        "aggregated": response.content,
        "strategy": aggregation_strategy,
        "subtask_count": len(results)
    }
