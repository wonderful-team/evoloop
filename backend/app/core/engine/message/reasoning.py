"""
reasoning.py — 推理内容提取工具函数
"""

from __future__ import annotations

from typing import Any

from app.core.engine.message.native_classes import BaseMessage
from app.infrastructure.llm.thinking_adapter import extract_reasoning_from_kwargs

__all__ = [
    "extract_reasoning_from_message",
    "extract_reasoning_from_kwargs",
    "extract_tool_calls",
]


def extract_reasoning_from_message(message: BaseMessage) -> str | None:
    """从消息中提取推理内容 (支持 Kimi/OpenAI/Anthropic 格式)"""
    # 1. Try additional_kwargs first
    reasoning = extract_reasoning_from_kwargs(message.additional_kwargs)
    if reasoning:
        return reasoning

    # 2. Extract Anthropic native thinking from content list
    if isinstance(message.content, list):
        anthropic_thinking = []
        for block in message.content:
            if (
                isinstance(block, dict)
                and block.get("type") == "thinking"
                and "thinking" in block
            ):
                anthropic_thinking.append(block["thinking"])
        if anthropic_thinking:
            return "".join(anthropic_thinking)

    return None


def extract_tool_calls(msg: Any) -> list[dict]:
    """
    归一化从消息中提取工具调用。
    """
    if hasattr(msg, "tool_calls"):
        return msg.tool_calls
    if isinstance(msg, dict):
        return msg.get("tool_calls", [])
    return []
