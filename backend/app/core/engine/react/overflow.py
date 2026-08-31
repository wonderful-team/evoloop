"""Model-aware context overflow detection (OpenCode `session/overflow.ts` semantic).

- ``usable(model)``：当前模型可用于历史的 token 预算（context × 0.6）减去预留输出
  token（对齐 OpenCode `model.limit.input - reserved`）。
- ``is_overflow(tokens, model)``：本次使用量是否已达到溢出线（≥ usable）。
- 由主循环在每轮完成后检查：溢出 → 触发结构化 compaction（react/compaction.py）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.infrastructure.llm.platform_service import llm_platform_service

logger = logging.getLogger(__name__)

#: 预留的 compaction 缓冲 token（对齐 OpenCode COMPACTION_BUFFER=20_000）
COMPACTION_BUFFER = 20_000
#: 历史 token 预算占 context 的比例（对齐 effective_history_tokens / REACT_BUDGET_RATIO）
HISTORY_RATIO = 0.6


def usable(
    model_name: str | None = None,
    *,
    cfg_reserved: int | None = None,
    output_token_max: int | None = None,
) -> int:
    """返回模型可用于历史的 token 预算；context 为 0 时返回 0（不可判定）。

    ``cfg_reserved``：显式预留（config.compaction.reserved 等价物）；
    默认 ``min(COMPACTION_BUFFER, output_token_max or model.max_tokens)``。
    """
    if not model_name:
        return 0
    profile = llm_platform_service.get_profile(model_name)
    context = int(profile.max_context_tokens or 0)
    if context <= 0:
        return 0
    budget = int(context * HISTORY_RATIO)
    reserved = (
        cfg_reserved
        if cfg_reserved is not None
        else min(COMPACTION_BUFFER, output_token_max or int(profile.max_tokens or 0))
    )
    return max(0, budget - reserved)


def is_overflow(
    total_tokens: int,
    model_name: str | None = None,
    *,
    cfg_reserved: int | None = None,
    output_token_max: int | None = None,
    auto: bool = True,
) -> bool:
    """判断当前使用量是否溢出（≥ usable）。

    ``auto=False``（config.compaction.auto=false 等价物）时恒为 False。
    """
    if not auto:
        return False
    limit = usable(model_name, cfg_reserved=cfg_reserved, output_token_max=output_token_max)
    if limit <= 0:
        return False
    return total_tokens >= limit


def overflow_status(
    total_tokens: int,
    model_name: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """溢出判定的可观测快照（供日志/埋点）。"""
    limit = usable(model_name, **{k: v for k, v in kwargs.items() if k in ("cfg_reserved", "output_token_max")})
    return {
        "total_tokens": total_tokens,
        "usable_tokens": limit,
        "is_overflow": is_overflow(total_tokens, model_name, **kwargs),
    }
