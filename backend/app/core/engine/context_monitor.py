"""
Context Monitor — Real-time context usage monitoring for Agent.

Provides context statistics (in **tokens**) to help the Agent track its budget;
上下文裁剪/工具输出折叠由系统自动管理（ContextTrimmer + executor 统一截断）。

All metrics are token-based and aligned with ContextTrimmer budgets.

口径修正（2026-09-19 值守日志实测）：此前 total 只估消息文本（len//4 英文
启发式，CJK 低估 ~4 倍）且完全不计工具面 Schema（实测 12-16k tok/请求，
最大缺失项）。修正为：①优先采用 provider 回报的上一请求实测 prompt_tokens
（``AIMessage.additional_kwargs["input_tokens"]``）+ 其后新增消息估算；
②无实测值时退回 CJK-aware 估算 + 工具面估算。口径随 dashboard 透出。
"""

import json
from typing import Any

from app.constants import DEFAULT_MAX_CONTEXT_TOKENS
from app.core.engine.message.native_classes import BaseMessage, ToolMessage
from app.core.engine.message.utils import get_message_text
from app.core.engine.schemas import ContextStats, ToolCallInfo
from app.infrastructure.llm.platform_service import llm_platform_service


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0xF900 <= cp <= 0xFAFF
        or 0x3000 <= cp <= 0x303F
        or 0xFF00 <= cp <= 0xFFEF
    )


def estimate_text_tokens(text: str) -> int:
    """CJK-aware token 估算（monitor 口径专用；不改动 trimmer 共用的 len//4）。

    中文 ~0.75 token/字（deepseek 系 tokenizer 经验值），其余 len/4。
    仅作无 provider 实测值时的兜底基线。
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if _is_cjk(ch))
    other = len(text) - cjk
    return max(1, int(cjk * 0.75 + other / 4))


def estimate_message_tokens_cjk(msg: Any) -> int:
    """monitor 口径的消息 token 估算：CJK-aware 文本 + 与 wire 一致的 overhead。

    不改 trimmer 共用的 ``estimate_message_tokens``（len//4），仅本模块用。
    """
    base = estimate_text_tokens(get_message_text(msg))
    overhead = 4
    tool_calls = (
        msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
    )
    role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "type", "")
    if role in ("assistant", "ai") and tool_calls:
        overhead += 8
    return base + overhead


class ContextMonitor:
    """Monitors and reports context usage for Agent awareness (token-based)."""

    @staticmethod
    def estimate_tools_tokens(tools_wire: list[dict] | None) -> int:
        """估算工具面（OpenAI wire 格式 tools 列表）token 占用。"""
        if not tools_wire:
            return 0
        return estimate_text_tokens(
            json.dumps(tools_wire, ensure_ascii=False)
        )

    @staticmethod
    def calculate(
        messages: list[BaseMessage],
        model: str | None = None,
        tools_tokens: int = 0,
    ) -> ContextStats:
        """
        Calculate context statistics from message list (token-based).

        Args:
            messages: Current message history
            model: Explicit model name. If not provided, uses a safe default.
            tools_tokens: 工具面估算（无 provider 实测基线时计入）。

        Returns:
            ContextStats with token-based usage information
        """
        if not model:
            max_tokens = DEFAULT_MAX_CONTEXT_TOKENS
        else:
            profile = llm_platform_service.get_profile(model)
            max_tokens = profile.max_context_tokens

        # ---- measured 优先：最近一条带 provider 实测 input_tokens 的 AI 消息 ----
        total_tokens = 0
        basis = "estimated"
        for j in range(len(messages) - 1, -1, -1):
            akw = getattr(messages[j], "additional_kwargs", None) or {}
            measured = akw.get("input_tokens")
            if isinstance(measured, int | float) and measured > 0:
                total_tokens = int(measured) + sum(
                    estimate_message_tokens_cjk(m) for m in messages[j + 1 :]
                )
                basis = "measured"
                break

        tool_tokens = 0
        tool_count = 0
        recent_tools: list[ToolCallInfo] = []

        if basis == "estimated":
            for i, msg in enumerate(messages):
                msg_tokens = estimate_message_tokens_cjk(msg)
                total_tokens += msg_tokens

                if isinstance(msg, ToolMessage):
                    tool_count += 1
                    tool_tokens += msg_tokens
                    recent_tools.append(
                        ToolCallInfo(
                            tool_call_id=msg.tool_call_id,
                            name=msg.name,
                            timestamp=float(i),  # Use index as timestamp proxy
                            token_count=msg_tokens,
                        )
                    )
            total_tokens += tools_tokens
        else:
            for i, msg in enumerate(messages):
                if isinstance(msg, ToolMessage):
                    tool_count += 1
                    tool_tokens += estimate_message_tokens_cjk(msg)
                    recent_tools.append(
                        ToolCallInfo(
                            tool_call_id=msg.tool_call_id,
                            name=msg.name,
                            timestamp=float(i),
                            token_count=estimate_message_tokens_cjk(msg),
                        )
                    )

        # Keep only last 5 tools
        recent_tools_summary = recent_tools[-5:]

        usage_ratio = min(total_tokens / max_tokens, 1.0) if max_tokens > 0 else 0.0

        return ContextStats(
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            message_count=len(messages),
            tool_message_count=tool_count,
            tool_tokens=tool_tokens,
            recent_tools=recent_tools_summary,
            usage_ratio=usage_ratio,
            tools_tokens=tools_tokens if basis == "estimated" else 0,
            basis=basis,
        )
