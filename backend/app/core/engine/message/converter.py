"""
EvoLoop Message Converter Utility (Native Python / Lightweight)
"""

import logging
from typing import Any

from app.core.engine.message.constants import MessageRole
from app.core.engine.message.native_classes import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)

# Backward-compatible aliases for external/OpenAI-style dict input.
_CANONICAL_ROLE: dict[str, MessageRole] = {
    "user": MessageRole.HUMAN,
    "assistant": MessageRole.AI,
    "human": MessageRole.HUMAN,
    "ai": MessageRole.AI,
    "system": MessageRole.SYSTEM,
    "tool": MessageRole.TOOL,
}


def _dict_to_message(d: dict) -> BaseMessage:
    """Convert a dict (with 'role' or 'type' key) to a native message object."""
    role = d.get("role") or d.get("type") or MessageRole.HUMAN
    canonical = _CANONICAL_ROLE.get(role, MessageRole.HUMAN)
    payload = {k: v for k, v in d.items() if k not in ("role", "type")}
    if canonical == MessageRole.AI:
        return AIMessage(**payload)
    if canonical == MessageRole.TOOL:
        return ToolMessage(**payload)
    if canonical == MessageRole.SYSTEM:
        return SystemMessage(**payload)
    return HumanMessage(**payload)


def _normalize_to_native(messages: list[Any]) -> list[BaseMessage]:
    result = []
    for m in messages:
        if isinstance(m, dict):
            result.append(_dict_to_message(m))
        elif isinstance(m, BaseMessage):
            result.append(m)
    return result


class EvoMessageConverter:
    @staticmethod
    def to_transport(messages: list[Any]) -> list[dict]:
        """Native → JSON-safe dict（跨进程/Celery 传输用）。

        原生 BaseMessage 经 ``model_dump`` 展开（role 用 canonical 值保留construct），
        供 worker 侧 ``repair()`` 还原；非原生项原样返回。
        """
        result: list[dict] = []
        for m in messages:
            if isinstance(m, BaseMessage):
                payload = m.model_dump(exclude_none=True)
                role_value = getattr(m.role, "value", m.role)
                payload.pop("role", None)
                result.append({"role": role_value, **payload})
            elif isinstance(m, dict):
                result.append(m)
        return result

    @staticmethod
    def repair(messages: list[Any]) -> list[BaseMessage]:
        """
        Ensure the message history is structurally valid for strict LLM APIs.
        Accepts native message objects or dicts; returns native objects.
        """
        msgs = _normalize_to_native(messages)

        from app.i18n.service import i18n

        _DEFAULTS = {
            "orphaned_tool": "[Tool execution context missing]",
            "interrupted_tool_response": "[Tool execution was interrupted]",
            "conversation_continuation": "[Conversation continues]",
        }

        def _t(key: str) -> str:
            try:
                result = i18n.get(f"core_utils.{key}", default=_DEFAULTS[key])
                return result if isinstance(result, str) else _DEFAULTS[key]
            except (KeyError, ValueError, AttributeError):
                return _DEFAULTS[key]

        # 1. Basic cleanup & orphaned tool repair
        stage1: list[BaseMessage] = []
        for msg in msgs:
            role = msg.role
            content = msg.content
            tool_calls = msg.tool_calls

            if not content and role not in (MessageRole.TOOL.value, MessageRole.AI.value):
                continue
            if role == MessageRole.AI and not content and not tool_calls:
                continue

            if role == MessageRole.TOOL:
                is_orphaned = True
                tool_call_id = msg.tool_call_id
                if stage1:
                    last = stage1[-1]
                    if last.role == MessageRole.AI and last.tool_calls:
                        ids = [
                            tc.get("id")
                            for tc in last.tool_calls
                            if isinstance(tc, dict)
                        ]
                        if tool_call_id in ids:
                            is_orphaned = False
                if is_orphaned:
                    stage1.append(
                        AIMessage(
                            content=_t("orphaned_tool"),
                            tool_calls=[
                                {
                                    "id": str(tool_call_id or "unknown_id"),
                                    "name": str(msg.name or "unknown_tool"),
                                    "args": {},
                                }
                            ],
                        )
                    )
                stage1.append(msg)
                continue

            if stage1:
                last = stage1[-1]
                if last.role == role and role in (MessageRole.HUMAN.value, MessageRole.AI.value):
                    if role == MessageRole.AI and last.tool_calls:
                        stage1.append(msg)
                        continue
                    if last.name == "context_ticket" or msg.name == "context_ticket":
                        stage1.append(msg)
                        continue
                    last.content = f"{last.content}\n\n{msg.content}"
                    continue

            stage1.append(msg)

        # 2. Dangling ToolCall repair
        final_repaired: list[BaseMessage] = []
        open_tool_calls: dict[str, str] = {}

        for msg in stage1:
            role = msg.role
            if role in (MessageRole.HUMAN.value, MessageRole.AI.value) and open_tool_calls:
                for tcid, tname in list(open_tool_calls.items()):
                    final_repaired.append(
                        ToolMessage(
                            content=_t("interrupted_tool_response"),
                            tool_call_id=tcid,
                            name=tname,
                        )
                    )
                open_tool_calls = {}

            if role == MessageRole.AI and msg.tool_calls:
                for tc in msg.tool_calls:
                    if isinstance(tc, dict):
                        tcid = tc.get("id")
                        tname = tc.get("name")
                        if tcid:
                            open_tool_calls[tcid] = tname or "unknown_tool"

            if role == MessageRole.TOOL and msg.tool_call_id in open_tool_calls:
                del open_tool_calls[msg.tool_call_id]

            final_repaired.append(msg)

        if open_tool_calls and final_repaired:
            for tcid, tname in list(open_tool_calls.items()):
                final_repaired.append(
                    ToolMessage(
                        content=_t("interrupted_tool_response"),
                        tool_call_id=tcid,
                        name=tname,
                    )
                )

        # 3. Ensure starting message
        non_system = [i for i, m in enumerate(final_repaired) if m.role != MessageRole.SYSTEM]
        if non_system:
            first = non_system[0]
            if final_repaired[first].role == MessageRole.AI:
                final_repaired.insert(
                    first, HumanMessage(content=_t("conversation_continuation"))
                )
        elif not final_repaired:
            final_repaired.append(HumanMessage(content=_t("conversation_continuation")))

        return final_repaired
