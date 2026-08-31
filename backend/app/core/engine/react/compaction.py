"""Structured context compaction (OpenCode `session/compaction.ts` semantic).

当上下文溢出（react/overflow.py 判定）时，把最早的旧消息经 LLM 总结为一条
摘要消息，替换进消息流——保留语义而非纯丢窗口。best-effort：LLM 失败时
退化为"丢弃前缀、保留最近尾部"的窗口裁剪。

保留策略（对齐 OpenCode）：
- 保留最近 ``preserve_recent_tokens`` 的尾部（usable × 25%，夹在 2k~15k）；
- 旧前缀压缩成一条摘要消息（模型仍可见要点）；
- ``PRUNE_PROTECTED_TOOLS={"skill"}``：压缩时 skill 正文作为高价值上下文保留。
"""

from __future__ import annotations

import logging

from app.core.engine.message.native_classes import BaseMessage, SystemMessage
from app.core.engine.message.utils import count_total_tokens, estimate_message_tokens

logger = logging.getLogger(__name__)

#: 至少压缩多少 token 才触发（太小不值得一次 LLM 总结）
PRUNE_MINIMUM = 20_000
#: 保留最近 token 的下限/上限（对齐 OpenCode MIN/MAX_PRESERVE_RECENT_TOKENS）
MIN_PRESERVE_RECENT_TOKENS = 2_000
MAX_PRESERVE_RECENT_TOKENS = 15_000
#: 压缩时保留不丢的高价值工具（skill 正文）
PRUNE_PROTECTED_TOOLS = {"skill"}


def preserve_recent_tokens(usable_tokens: int) -> int:
    """本次要保留的最近尾部 token 预算（usable × 25%，夹在 2k~15k）。"""
    return min(
        MAX_PRESERVE_RECENT_TOKENS,
        max(MIN_PRESERVE_RECENT_TOKENS, int((usable_tokens or 0) * 0.25)),
    )


def find_tail_start(messages: list[BaseMessage], preserve_tokens: int) -> int:
    """从尾部向前累加，找到覆盖 preserve_tokens 的最近尾部起点下标。

    返回 0 表示整段都需要保留（无可压缩前缀）。
    """
    budget = 0
    for i in range(len(messages) - 1, -1, -1):
        budget += estimate_message_tokens(messages[i])
        if budget >= preserve_tokens:
            return i
    return 0


def _serialize_prefix(prefix: list[BaseMessage], max_chars: int = 200_000) -> str:
    """把待压缩的前缀序列化成纯文本，供 LLM 总结。"""
    lines: list[str] = []
    for msg in prefix:
        role = getattr(msg, "role", "?")
        name = getattr(msg, "name", None)
        tool_calls = getattr(msg, "tool_calls", None)
        content = str(getattr(msg, "content", "") or "")
        if role == "human":
            lines.append(f"[用户]: {content[:2000]}")
        elif role == "assistant":
            if tool_calls:
                calls = ", ".join(
                    f"{tc.get('name')}({str(tc.get('args'))[:200]})"
                    for tc in tool_calls
                    if isinstance(tc, dict)
                )
                lines.append(f"[助手调用工具]: {calls}")
                if content:
                    lines.append(f"[助手]: {content[:2000]}")
            else:
                lines.append(f"[助手]: {content[:2000]}")
        elif role == "tool":
            # 高价值工具正文（如 skill）保留原文；其余截断
            if name in PRUNE_PROTECTED_TOOLS:
                lines.append(f"[工具 {name}]: {content[:8000]}")
            else:
                lines.append(f"[工具 {name}]: {content[:500]}")
    text = "\n".join(lines)
    return text[:max_chars]


async def _summarize(prefix: list[BaseMessage], model: str | None, config: dict) -> str:
    """调用 LLM 生成旧前缀的结构化摘要；失败返回空串。"""
    try:
        from app.infrastructure.llm.factory import LLMFactory
        from app.infrastructure.schemas import LLMConfig
        from app.utils.prompt_loader import render_prompt

        llm = await LLMFactory.create_llm(
            LLMConfig(model_name=model or "", temperature=0.2, streaming=False)
        )
        history = _serialize_prefix(prefix)
        prompt = render_prompt("core/engine/compaction.txt", {"history": history})
        lc_config = {"configurable": (config or {}).get("configurable", {})}
        resp = await llm.ainvoke(prompt, config=lc_config)
        summary = str(getattr(resp, "content", "") or "").strip()
        return summary[:4000]
    except Exception as e:
        logger.warning(f"[Compaction] summarize failed: {e}", exc_info=True)
        return ""


async def compact_messages(
    messages: list[BaseMessage],
    model: str | None,
    config: dict,
    *,
    usable_tokens: int,
    min_compact_tokens: int = PRUNE_MINIMUM,
) -> tuple[list[BaseMessage], bool]:
    """压缩旧前缀为一条摘要消息，返回 (新消息流, 是否发生压缩)。

    压缩前后 token 减少不足 ``min_compact_tokens`` 时不压缩（避免无谓的 LLM 调用）。
    """
    if len(messages) < 4 or usable_tokens <= 0:
        return messages, False

    preserve = preserve_recent_tokens(usable_tokens)
    tail_start = find_tail_start(messages, preserve)
    if tail_start <= 0:
        return messages, False

    prefix = messages[:tail_start]
    tail = messages[tail_start:]

    before_tokens = count_total_tokens(messages)
    prefix_tokens = count_total_tokens(prefix)
    if prefix_tokens < min_compact_tokens:
        return messages, False

    summary = await _summarize(prefix, model, config)
    if summary:
        summary_msg = SystemMessage(
            content=(
                "[Context Compaction] 以下为早期对话/任务上下文的结构化摘要"
                "（原始消息已压缩释放空间，不影响后续任务）：\n\n"
                + summary
            )
        )
    else:
        summary_msg = SystemMessage(
            content=(
                "[Context Compaction] 早期上下文已被系统压缩"
                "（原始消息略过，最新上下文见后续消息）。"
            )
        )

    compacted = [summary_msg] + tail
    after_tokens = count_total_tokens(compacted)
    logger.info(
        f"[Compaction] prefix={len(prefix)}msgs/{prefix_tokens}tok -> summary, "
        f"total {before_tokens} -> {after_tokens} tokens"
    )
    return compacted, True
