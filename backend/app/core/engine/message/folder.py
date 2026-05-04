"""
MessageNormalizer - 消息规范化工具类

统一处理消息由扁平结构（DB/Dict）向规范化结构（MessageBlock）的转换逻辑。
遵循“即读即显”原则，移除冗余的 LangChain 对象转换层。
"""
import logging
from datetime import datetime
from typing import Any, Union

from app.core.engine.message.schemas import MessageBlock
from app.core.tools.registry import get_tool_metadata
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


class MessageNormalizer:
    """
    Utility for normalizing messages into a consistent format.
    Supports SQLAlchemy models, dicts, and LangChain messages.
    """

    @staticmethod
    def _get_val(obj: Any, key: str, default: Any = None) -> Any:
        """Universal getter for dicts or objects."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @classmethod
    def normalize_dict(cls, msg: Union[dict, Any]) -> dict:
        """
        Normalizes a single message (as a dict).
        Self-sufficient normalization based on current message data.
        """
        # Convert to dict if it's an object, for easier manipulation
        if not isinstance(msg, dict):
            meta_data = getattr(msg, "meta_data", None)
            if not isinstance(meta_data, dict):
                # Fallback for LangChain messages
                meta_data = getattr(msg, "metadata", None)
                if not isinstance(meta_data, dict):
                    meta_data = {}
            msg_dict = {
                "role": getattr(msg, "role", "unknown"),
                "content": getattr(msg, "content", ""),
                "tool_name": getattr(msg, "tool_name", None),
                "tool_call_id": getattr(msg, "tool_call_id", None),
                "meta_data": meta_data
            }
        else:
            msg_dict = msg

        role = msg_dict.get("role")
        
        if role == "tool":
            tool_name = msg_dict.get("tool_name")
            tool_call_id = msg_dict.get("tool_call_id") or msg_dict.get("id")
            
            # Extract arguments
            meta = msg_dict.get("meta_data") or {}
            args = msg_dict.get("input") or msg_dict.get("args") or meta.get("input") or {}
            
            # Resolve display name via i18n
            tool_meta_reg = get_tool_metadata(tool_name) or {}
            summary_template = tool_meta_reg.summary_template if hasattr(tool_meta_reg, "summary_template") else None
            
            tool_name_display = None
            if summary_template:
                tool_name_display = i18n.get(summary_template, **args)

            if not tool_name_display or tool_name_display == summary_template:
                tool_name_display = tool_name.replace("_", " ").title() if tool_name else "Unknown Tool"

            tool_meta = {
                "affected_path_keys": getattr(tool_meta_reg, "affected_path_keys", []),
                "display_name": tool_name_display,
            }

            msg_dict.update({
                "role": "tool",
                "content": "",
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "input": args,
                "tool_meta": tool_meta,
                "meta_data": {
                    **meta,
                    "tool_meta": tool_meta,
                    "input": args
                }
            })
        return msg_dict

    @classmethod
    def normalize(cls, messages: list[Any]) -> list[MessageBlock]:
        """
        Maps a list of raw messages (DB records or dicts) directly to MessageBlock.
        """
        result: list[MessageBlock] = []

        for msg in messages:
            role = cls._get_val(msg, "role")
            
            # 1. Filter hidden tools immediately
            if role == "tool":
                tool_name = cls._get_val(msg, "tool_name")
                tool_meta = get_tool_metadata(tool_name)
                if tool_meta and tool_meta.is_hidden:
                    continue

            # 2. Extract common fields
            msg_id = str(cls._get_val(msg, "id"))
            content = cls._get_val(msg, "content", "")
            thinking = cls._get_val(msg, "thinking")
            status = cls._get_val(msg, "status", "completed")
            created_at = cls._get_val(msg, "created_at")
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()

            meta_data = cls._get_val(msg, "meta_data") or {}
            if not isinstance(meta_data, dict):
                meta_data = {}
            
            # 3. Handle Specific Roles
            if role == "ai":
                # Handle tool_calls serialization (ensure it's a list of dicts)
                raw_tool_calls = cls._get_val(msg, "tool_calls") or []
                serializable_tool_calls = []
                for tc in raw_tool_calls:
                    tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    tc_meta = get_tool_metadata(tc_name)
                    if tc_meta and tc_meta.is_hidden:
                        continue
                        
                    if isinstance(tc, dict):
                        serializable_tool_calls.append(tc)
                    elif hasattr(tc, "model_dump"):
                        serializable_tool_calls.append(tc.model_dump())
                    elif hasattr(tc, "dict"):
                        serializable_tool_calls.append(tc.dict())
                    else:
                        serializable_tool_calls.append(dict(tc))

                result.append(MessageBlock(
                    id=msg_id,
                    role="ai",
                    content=content,
                    thinking=thinking,
                    tool_calls=serializable_tool_calls,
                    created_at=created_at,
                    status=status,
                    meta_data=meta_data,
                    thread_id=str(cls._get_val(msg, "conversation_id", ""))
                ))

            elif role == "tool":
                # Normalize tool data
                normalized = cls.normalize_dict(msg)
                result.append(MessageBlock(
                    id=msg_id,
                    role="tool",
                    content=content,
                    created_at=created_at,
                    tool_name=normalized.get("tool_name"),
                    tool_call_id=normalized.get("tool_call_id"),
                    input=normalized.get("input"),
                    tool_meta=normalized.get("tool_meta"),
                    meta_data=normalized["meta_data"],
                    thread_id=str(cls._get_val(msg, "conversation_id", ""))
                ))

            elif role in ("human", "user"):
                result.append(MessageBlock(
                    id=msg_id,
                    role="human",
                    content=content,
                    created_at=created_at,
                    status=status,
                    meta_data=meta_data,
                    thread_id=""
                ))

            elif role == "system":
                result.append(MessageBlock(
                    id=msg_id, 
                    role="system", 
                    content=content,
                    created_at=created_at,
                    meta_data=meta_data,
                    thread_id=""
                ))

        return result
