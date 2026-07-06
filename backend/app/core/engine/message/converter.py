"""
EvoLoop Message Converter Utility (Native Python / Lightweight)
"""

import logging
from typing import Any

from app.core.engine.message.utils import normalize_tool_calls

logger = logging.getLogger(__name__)


class EvoMessageConverter:
    """
    Unified converter for system-wide message normalization (SDK-free).
    """

    @staticmethod
    def to_dict(msg: Any) -> dict:
        """
        Convert any message (native BaseMessage, DB object, dict) to standard native dict.
        """
        if isinstance(msg, dict):
            return msg

        role = getattr(msg, "role", None)
        if not role:
            msg_type = getattr(msg, "type", "user")
            if msg_type == "human":
                role = "user"
            elif msg_type == "ai":
                role = "assistant"
            else:
                role = msg_type

        content = getattr(msg, "content", "")
        additional_kwargs = getattr(msg, "additional_kwargs", {}) or {}

        metadata = getattr(msg, "metadata", {}) or {}
        if metadata:
            additional_kwargs = {**additional_kwargs, **metadata}

        res = {
            "role": role,
            "content": content,
            "additional_kwargs": additional_kwargs,
        }

        msg_id = getattr(msg, "id", None)
        if msg_id:
            res["id"] = msg_id

        msg_name = getattr(msg, "name", None)
        if msg_name:
            res["name"] = msg_name

        if hasattr(msg, "tool_calls") and msg.tool_calls:
            res["tool_calls"] = normalize_tool_calls(msg.tool_calls)
        if hasattr(msg, "tool_call_id"):
            res["tool_call_id"] = getattr(msg, "tool_call_id")

        return res

    @staticmethod
    def to_message_dicts(messages: list[Any]) -> list[dict]:
        """
        Normalize a list of messages to standard dicts.
        """
        _TYPE_TO_ROLE = {
            "human": "user",
            "ai": "assistant",
            "system": "system",
            "tool": "tool",
        }

        deserialized = []
        for m in messages:
            if isinstance(m, dict):
                if "role" not in m and "type" in m:
                    m = {**m, "role": _TYPE_TO_ROLE.get(m["type"], "user")}
                deserialized.append(m)
                continue
            try:
                raw = m.model_dump() if hasattr(m, "model_dump") else {}
                role = raw.get("role") or _TYPE_TO_ROLE.get(raw.get("type"), "user")
                msg_dict = {"role": role, "content": raw.get("content", "")}
                for key in ("tool_calls", "tool_call_id", "name", "additional_kwargs", "id", "metadata"):
                    if key in raw:
                        msg_dict[key] = raw[key]
                deserialized.append(msg_dict)
            except (AttributeError, ValueError, TypeError):
                continue
        return deserialized

    @staticmethod
    def from_message_dicts(messages: list[dict]) -> list[dict]:
        """Convert messages directly to standard dicts."""
        return list(messages)

    @staticmethod
    def repair(messages: list[Any]) -> list[dict]:
        """
        Ensure the message history is structurally valid for strict LLM APIs.
        """
        # Normalize mixed dict/model to dicts
        messages = EvoMessageConverter.to_message_dicts(messages)

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
        stage1: list[dict] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")

            if not content and role not in ("tool", "assistant"):
                continue
            if role == "assistant" and not content and not tool_calls:
                continue

            if role == "tool":
                is_orphaned = True
                tool_call_id = msg.get("tool_call_id")
                if stage1:
                    last = stage1[-1]
                    if last.get("role") == "assistant" and last.get("tool_calls"):
                        ids = [tc.get("id") for tc in last["tool_calls"] if isinstance(tc, dict)]
                        if tool_call_id in ids:
                            is_orphaned = False
                if is_orphaned:
                    stage1.append({
                        "role": "assistant",
                        "content": _t("orphaned_tool"),
                        "tool_calls": [
                            {
                                "id": str(tool_call_id or "unknown_id"),
                                "name": str(msg.get("name") or "unknown_tool"),
                                "args": {},
                            }
                        ]
                    })
                stage1.append(msg)
                continue

            if stage1:
                last = stage1[-1]
                if last.get("role") == role and role in ("user", "assistant"):
                    if role == "assistant" and last.get("tool_calls"):
                        stage1.append(msg)
                        continue
                    if last.get("name") == "context_ticket" or msg.get("name") == "context_ticket":
                        stage1.append(msg)
                        continue
                    last["content"] = f"{last.get('content', '')}\n\n{msg.get('content', '')}"
                    continue

            stage1.append(dict(msg))

        # 2. Dangling ToolCall repair
        final_repaired: list[dict] = []
        open_tool_calls: dict[str, str] = {}

        for msg in stage1:
            role = msg.get("role")
            if role in ("user", "assistant") and open_tool_calls:
                for tcid, tname in list(open_tool_calls.items()):
                    final_repaired.append({
                        "role": "tool",
                        "content": _t("interrupted_tool_response"),
                        "tool_call_id": tcid,
                        "name": tname,
                    })
                open_tool_calls = {}

            if role == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict):
                        tcid = tc.get("id")
                        tname = tc.get("name")
                        if tcid:
                            open_tool_calls[tcid] = tname or "unknown_tool"

            if role == "tool" and msg.get("tool_call_id") in open_tool_calls:
                del open_tool_calls[msg["tool_call_id"]]

            final_repaired.append(msg)

        if open_tool_calls and final_repaired:
            for tcid, tname in list(open_tool_calls.items()):
                final_repaired.append({
                    "role": "tool",
                    "content": _t("interrupted_tool_response"),
                    "tool_call_id": tcid,
                    "name": tname,
                })

        # 3. Ensure starting message
        non_system = [
            i for i, m in enumerate(final_repaired) if m.get("role") != "system"
        ]
        if non_system:
            first = non_system[0]
            if final_repaired[first].get("role") == "assistant":
                final_repaired.insert(
                    first, {"role": "user", "content": _t("conversation_continuation")}
                )
        elif not final_repaired:
            final_repaired.append({"role": "user", "content": _t("conversation_continuation")})

        return final_repaired
