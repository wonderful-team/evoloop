"""React engine main loop — single-Agent ReAct (OpenCode `runLoop` semantic).

主 Agent 一条连续消息流执行完整 ReAct：LLM 调用 → 工具执行 → 结果回灌，
直到无 tool_calls 的文本回复结束。

执行内核是 OpenHands SDK（``sdk_adapter/session_bridge``）：
- 卡死检测：SDK StuckDetector（5 类模式，触发后转 HITL 问人）；
- 上下文治理：SDK condensation；
- 循环/事件/工具桥接：见 docs/openhands-sdk-integration.md。
"""

from __future__ import annotations

import logging
from typing import Any

from app.constants import DEFAULT_MAX_CONTEXT_TOKENS
from app.core.config import settings

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
    state: Any,
    config: dict[str, Any],
    thread_id: str,
    *,
    max_steps: int | None = None,
    log_prefix: str = "Agent",
    steer_provider: Any | None = None,
) -> dict[str, Any]:
    """执行单 Agent ReAct 主循环（同步阻塞一轮 delivery）。

    步数上限默认按当前模型上下文大小动态缩放（config.py），可被显式入参覆盖。
    返回 dict（tool_history / is_truncated / outcome）。
    """
    if max_steps is None:
        model_name = (config or {}).get("configurable", {}).get("model")
        max_steps = resolve_max_steps(model_name)

    from app.core.engine.sdk_adapter.session_bridge import run_turn

    return await run_turn(
        state=state,
        config=config,
        thread_id=thread_id,
        max_steps=max_steps,
        log_prefix=log_prefix,
        steer_provider=steer_provider,
    )
