"""React engine main loop — single-Agent ReAct (OpenCode `runLoop` semantic).

主 Agent 一条连续消息流执行完整 ReAct：LLM 调用 → 工具执行 → 结果回灌，
直到无 tool_calls 的文本回复结束。无图节点切换、无消息过滤、无 ticket。

复用了 ``AgentEngine.run_react_loop`` —— 它内部即完整单 ReAct（create_llm →
bind_tools → trim → run_react_loop → tool_executor）。本模块只负责：
- 构建单 Agent system prompt（main.txt + 动态索引块）
- 解析 react 节点工具池
- 执行并写回状态
"""

from __future__ import annotations

import logging
from typing import Any

from app.constants import DEFAULT_MAX_CONTEXT_TOKENS
from app.core.config import settings
from app.core.engine.react.prompts import build_system_prompt
from app.core.engine.schemas import EngineResult, RunOutcome, RunOutcomeStatus
from app.core.engine.state import AgentState
from app.core.exceptions import DoomLoopException

logger = logging.getLogger(__name__)


def resolve_max_steps(
    model_name: str | None,
    base: int | None = None,
    *,
    min_steps: int | None = None,
    max_steps: int | None = None,
) -> int:
    """按模型上下文大小等比缩放 max_steps，并钳制到 [min, max]。

    - base：基准步数（默认 settings.AGENT_MAX_STEPS，对应 128k 上下文）。
    - context 不可判定（无模型或无 profile）时回退 base。
    - 缩放保持 128k 语义：128k → base，256k → 2×base，64k → 0.5×base。
    """
    base = base or settings.AGENT_MAX_STEPS
    lo = min_steps if min_steps is not None else settings.AGENT_MAX_STEPS_MIN
    hi = max_steps if max_steps is not None else settings.AGENT_MAX_STEPS_MAX

    if not model_name:
        return min(max(base, lo), hi)

    try:
        from app.infrastructure.llm.platform_service import llm_platform_service

        profile = llm_platform_service.get_profile(model_name)
        context = int(profile.max_context_tokens or 0)
    except Exception as e:  # noqa: BLE001 - 上下文解析失败只影响步数上限，必须容错
        logger.warning(
            f"[ReactLoop] resolve_max_steps profile lookup failed for {model_name}: {e}",
            exc_info=True,
        )
        context = 0

    if context <= 0:
        return min(max(base, lo), hi)

    ref = int(DEFAULT_MAX_CONTEXT_TOKENS) or 128_000
    scaled = round(base * context / ref)
    return min(max(scaled, lo), hi)


async def run_agent_loop(
    state: AgentState,
    config: dict[str, Any],
    thread_id: str,
    *,
    max_steps: int | None = None,
    log_prefix: str = "ReactAgent",
    steer_provider: Any | None = None,
) -> dict[str, Any]:
    """执行单 Agent ReAct 主循环（同步阻塞一轮 delivery）。

    返回与 ``AgentEngine.run_react_loop`` 一致的 dict（messages / tool_history /
    is_truncated / outcome）。
    """
    from app.core.engine.engine import AgentEngine

    # 步数上限默认按当前模型上下文大小动态缩放（config.py），可被显式入参覆盖。
    if max_steps is None:
        model_name = (config or {}).get("configurable", {}).get("model")
        max_steps = resolve_max_steps(model_name)

    engine = AgentEngine()
    name = log_prefix or "Agent"

    # 1. 构建单 Agent system prompt（静态人格 + 动态索引块）
    system_prompt = await build_system_prompt(state, config)

    # 2. 解析工具池：子代理按类型裁剪工具面（visibleTools 语义，不在面内即不可见）；
    #    主 Agent 用 react 全量面。复用 manager（含 VISION_MODEL 过滤）后按面裁剪。
    from app.core.tools.manager import tool_manager

    tools = await tool_manager.get_agent_tools("react", state)
    _meta = (config or {}).get("metadata") or {}
    subagent_tools = _meta.get("subagent_tools")
    if subagent_tools:
        allowed = set(subagent_tools)
        tools = [t for t in tools if t.name in allowed]
        if not tools:
            logger.warning("[ReactTask] subagent tool face resolved empty; using react face")

    # 3. 执行完整 ReAct（AgentEngine.run_react_loop 即单 ReAct，不进图）
    try:
        result = await engine.run_react_loop(
            state=state,
            config=config,
            system_prompt=system_prompt,
            tools=tools,
            max_steps=max_steps,
            temperature=0.7,
            name=name,
            # 对齐 OpenCode 并行工具调用（单消息多 tool call 并发，尤其多 task 并行子代理）
            parallel_tools=True,
            model=config.get("configurable", {}).get("model"),
            steer_provider=steer_provider,
        )
    except DoomLoopException as e:
        # 代码层防循环：问用户继续还是停止（对齐 OpenCode permission.ask("doom_loop"")）。
        # HITL 挂起 → 用户答复后会话恢复；docker/无 HITL 时降级为确定性收尾。
        logger.warning(f"[{name}] Doom-loop guard triggered: {e}")
        from app.core.exceptions import AgentHumanInterruptException
        from app.core.hitl.core import (
            create_request,
            push_hitl_notification,
            raise_hitl_interrupt,
        )

        try:
            request = await create_request(
                thread_id=thread_id,
                request_type="choice",
                prompt=(
                    f"检测到连续重复的相同工具调用（{str(e)[:200]}），"
                    "为避免无限循环，是否停止本轮？"
                ),
                options=["停止", "继续"],
                default_value="停止",
            )
            await push_hitl_notification(
                thread_id=thread_id,
                request=request,
                request_data={
                    "id": request.id,
                    "type": "choice",
                    "prompt": request.description,
                    "options": ["停止", "继续"],
                    "default_value": "停止",
                },
                project_id=state.project_id,
                tool_name="doom_loop",
            )
            raise_hitl_interrupt(
                request.id, "Doom-loop guard: 请选择停止或继续"
            )
        except AgentHumanInterruptException:
            raise  # 挂起等用户答复，恢复后继续
        except Exception as h_err:
            logger.warning(
                f"[{name}] doom_loop ask failed, fallback to deterministic stop: {h_err}",
                exc_info=True,
            )

        from app.core.engine.message.native_classes import AIMessage

        result = EngineResult(
            messages=[
                AIMessage(
                    content=(
                        "已自动停止：检测到连续重复的相同工具调用，为避免无限循环"
                        "提前终止本轮任务。可补充说明或调整指令后重试。"
                    )
                )
            ],
            tool_history=state.tool_history or [],
            is_truncated=True,
            outcome=RunOutcome(status=RunOutcomeStatus.TRUNCATED),
        )

    # 4. 写回状态
    state.tool_history = result.tool_history

    # 5. 收尾管线（react 替代 FinishNode）：SESSION_COMPLETED + 记忆/宏学习闭环
    summary = _extract_summary(result.messages)
    from app.core.engine.react.completion import publish_session_completed_react

    try:
        await publish_session_completed_react(
            thread_id, state.project_id, config, state, summary=summary
        )
    except Exception as e:
        logger.warning(f"[ReactLoop] completion pipeline failed: {e}")

    return {
        "messages": result.messages,
        "tool_history": result.tool_history,
        "is_truncated": result.is_truncated,
        "outcome": result.outcome.status,
    }


def _extract_summary(messages: list[Any]) -> str:
    """提取最终 assistant 文本作为 summary（供收尾管线与事件）。"""
    for msg in reversed(messages or []):
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", "")
        if role in ("ai", "assistant") and content and not getattr(msg, "tool_calls", None):
            return str(content)[:2000]
    return ""
