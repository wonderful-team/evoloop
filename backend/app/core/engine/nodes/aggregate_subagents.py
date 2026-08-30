"""AggregateSubagentsNode — aggregate N subagent results.

Design: docs/subagent-design.md §4.2.
"""

import json
import logging

from app.core.engine.message.native_classes import AIMessage
from app.core.engine.message.repository import MessageRepository
from app.core.engine.nodes.base import BaseNode
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate
from app.models.subagent import SubagentStatus

logger = logging.getLogger(__name__)


class AggregateSubagentsNode(BaseNode):
    """聚合 N 个 subagent 的结果。"""

    def __init__(self):
        super().__init__(node_name="AggregateSubagents")

    async def __call__(self, state: AgentState, config: dict) -> StateUpdate:
        results = state.completed_subagents or []
        pending = state.pending_subagent_aggregation

        if not results:
            logger.warning("[AggregateSubagents] No completed subagents to aggregate")
            return StateUpdate(next_node=RoutingTarget.SUPERVISOR)

        if not pending:
            logger.warning("[AggregateSubagents] No pending aggregation config")
            return StateUpdate(next_node=RoutingTarget.SUPERVISOR)

        strategy = pending.get("strategy", "merge")
        logger.info(
            f"[AggregateSubagents] Aggregating {len(results)} results with strategy '{strategy}'"
        )

        aggregated = await aggregate_results(
            results, strategy, pending.get("parent_task", "")
        )

        agg_msg = AIMessage(content=aggregated)

        # 追加而非替换：merge_state_update 对 messages 是直接写入，用它替换会
        # 清空当前会话上下文；聚合消息应追加到已有消息之后。
        existing_messages = list(state.messages or [])

        # 聚合结果落库为一条可见 assistant 消息：后续任何基于 DB 重建的
        # Supervisor 上下文都会看到聚合内容（字段/内存里的聚合消息可能因
        # 事件驱动的重建而丢失，B2 曾出现仅剩 LLM 安抚语而丢结果）。
        try:
            if getattr(state, "thread_id", None):
                repo = MessageRepository(
                    state.thread_id, project_id=getattr(state, "project_id", None)
                )
                await repo.persist(
                    role="ai",
                    content=aggregated,
                    category="aggregation",
                    is_visible=True,
                    node_source="aggregate_subagents",
                    metadata={"parent_task": pending.get("parent_task", "")[:200]},
                )
        except Exception:
            logger.warning(
                "[AggregateSubagents] Failed to persist aggregate message",
                exc_info=True,
            )

        return StateUpdate(
            # 强制呈现标记：Supervisor 收到后禁止重新委派，必须直接呈现聚合结果
            # （否则 LLM 在聚合轮仍可能再次 route_to/spawn，导致结果不呈现）。
            messages=existing_messages + [agg_msg],
            last_aggregation_result=aggregated,
            presentation_pending=True,
            completed_subagents=[],
            pending_subagent_aggregation=None,
            subagent_aggregation_turn=False,
            next_node=RoutingTarget.SUPERVISOR,
        )


async def aggregate_results(
    results: list[dict], strategy: str, original_task: str
) -> str:
    """Aggregate N subagent results into one text (reusable by Worker split mode).

    ``results`` items: {"subagent_id", "status", "result"}.
    """
    if strategy == "concatenate":
        return _concatenate(results)
    try:
        aggregated = await _llm_aggregate(results, strategy, original_task)
        # 聚合 LLM 可能返回空/纯空白内容（配额、超时、格式异常等），
        # 必须兜底为拼接，否则 last_aggregation_result 为空导致呈现丢数据。
        if not str(aggregated or "").strip():
            raise ValueError("LLM aggregation returned empty content")
        return aggregated
    except Exception as e:
        # Phase E2：聚合 LLM 失败 → 降级为简单拼接，不让聚合崩溃拖垮 Worker。
        logger.warning(
            f"[AggregateSubagents] LLM aggregation failed ({e}); "
            "falling back to concatenate",
            exc_info=True,
        )
        return _concatenate(results)


def _concatenate(results: list[dict]) -> str:
    """简单拼接（含失败项如实标注，N 成功 M 失败）。"""
    items = []
    success = 0
    failed = 0
    for r in results:
        status = r.get("status", "unknown")
        result = str(r.get("result", "")).strip()
        if status == SubagentStatus.COMPLETED:
            success += 1
            items.append(result)
        else:
            failed += 1
            err = r.get("error") or "unknown error"
            items.append(
                f"[{status}] {r.get('subagent_id', 'unknown')}: {result or err}"
            )
    joined = "\n\n---\n\n".join(i for i in items if i)
    header = f"聚合摘要（{success} 成功，{failed} 失败）"
    if not joined:
        return header
    return f"{header}\n\n{joined}"


async def _llm_aggregate(results: list[dict], strategy: str, original_task: str) -> str:
    from app.infrastructure.llm import InternalLLMService
    from app.utils.template import render_template

    raw_results = [
        {
            "subagent_id": r.get("subagent_id", "unknown"),
            "status": r.get("status", "unknown"),
            "result": r.get("result", ""),
        }
        for r in results
    ]

    prompt = render_template(
        "core/engine/subagent_aggregate.prompt.j2",
        original_task=original_task,
        strategy=strategy,
        results_json=json.dumps(raw_results, ensure_ascii=False),
    )

    response = await InternalLLMService.invoke(
        messages=[{"role": "user", "content": prompt}],
        purpose="subagent_aggregation",
        temperature=0.3,
    )
    content = response.content
    # OpenAI 风格的 list-of-text-blocks 归一化为纯文本。
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        content = "".join(parts)
    return str(content or "")
