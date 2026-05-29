"""
MessageBlockFactory - 统一视图层出厂转换器

负责将底层的 ORM 模型或运行时的碎片化内存事件统一转换为前端严格依赖的 `MessageBlock` 契约结构。
解决历史记录和流式事件结构分裂的问题。
"""
import json
import logging
from datetime import datetime
from typing import Any, Union

from app.core.engine.message.schemas import MessageBlock, ToolCall
from app.core.engine.message.utils import normalize_tool_calls
from app.core.tools.registry import get_tool_metadata

logger = logging.getLogger(__name__)


class MessageBlockFactory:
    """
    Unified factory for constructing valid MessageBlock objects from different data sources.
    """

    @staticmethod
    def _get_val(obj: Any, key: str, default: Any = None) -> Any:
        """Universal getter for dicts or objects."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @classmethod
    def from_orm(cls, msg: Any) -> MessageBlock:
        """
        Creates a MessageBlock from a database Message ORM model.
        """
        role = cls._get_val(msg, "role", "unknown")
        msg_id = str(cls._get_val(msg, "id"))
        content = cls._get_val(msg, "content", "")
        thinking = cls._get_val(msg, "thinking")
        status = cls._get_val(msg, "status", "completed")
        created_at = cls._get_val(msg, "created_at")
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()

        thread_id = str(cls._get_val(msg, "thread_id", ""))

        # 兼容旧版数据：部分遗留记录使用 conversation_id 而非 thread_id
        # 新数据统一使用 thread_id (MessageBlock 标准字段)
        if not thread_id:
            thread_id = str(cls._get_val(msg, "conversation_id", ""))

        meta_data = cls._get_val(msg, "meta_data") or {}
        if not isinstance(meta_data, dict):
            meta_data = {}

        # 3. Handle References (if present in ORM)
        from app.core.engine.message.schemas import ReferenceBlock
        references = []
        if hasattr(msg, "references") and msg.references:
            for ref in msg.references:
                ref_block = ReferenceBlock(
                    id=ref.id,
                    type=ref.type,
                    target_id=ref.target_id,
                    target_name=ref.target_name,
                    meta_data=ref.meta_data or {},
                )
                references.append(ref_block)

        # 4. Human / System / AI / Tool
        if role == "ai":
            raw_tool_calls = cls._get_val(msg, "tool_calls") or []
            serializable_tool_calls = []

            # Normalize and filter hidden tool calls
            for tc in normalize_tool_calls(raw_tool_calls):
                tc_name = tc.get("name")
                tc_meta = get_tool_metadata(tc_name) if tc_name else None
                if tc_meta and tc_meta.is_hidden:
                    continue

                # Convert to ToolCall model to ensure strict validation and correct serialization
                serializable_tool_calls.append(ToolCall(**tc))

            return MessageBlock(
                id=msg_id,
                role="ai",
                content=content,
                thinking=thinking,
                tool_calls=serializable_tool_calls,
                references=references,
                created_at=created_at or "",
                status=status,
                meta_data=meta_data,
                thread_id=thread_id
            )

        elif role == "tool":
            tool_name = cls._get_val(msg, "tool_name")
            tool_call_id = cls._get_val(msg, "tool_call_id") or msg_id

            input_args = cls._get_val(msg, "input") or cls._get_val(msg, "args") or meta_data.get("input") or {}
            output = meta_data.get("output", content)

            # ... (Existing tool_meta logic) ...
            metadata_registry = get_tool_metadata(tool_name) if tool_name else None
            summary_args = {**input_args} # Simple fallback for now
            display_name = metadata_registry.get_display_name(tool_name, summary_args) if metadata_registry and tool_name else (tool_name or "Unknown").replace("_", " ").title()

            tool_meta = {
                "display_name": display_name,
                "affected_path_keys": metadata_registry.affected_path_keys if metadata_registry else [],
            }

            return MessageBlock(
                id=msg_id,
                role="tool",
                content=content,
                created_at=created_at or "",
                status=status,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                input=input_args,
                tool_meta=tool_meta,
                references=references,
                meta_data={**meta_data, "tool_meta": tool_meta},
                thread_id=thread_id
            )

        else:
            return MessageBlock(
                id=msg_id,
                role=role, # type: ignore
                content=content,
                references=references,
                created_at=created_at or "",
                status=status,
                meta_data=meta_data,
                thread_id=thread_id
            )

    @classmethod
    def from_event(
        cls,
        thread_id: str,
        sequence_number: int,
        role: str,
        content: str | None = None,
        thinking: str | None = None,
        tool_calls: list | None = None,
        category: str = "",
        status: str = "completed",
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        metadata: dict | None = None,
        parent_id: str | None = None,
        run_id: str | None = None,
        references: list | None = None,
        message_id: str | None = None,
    ) -> MessageBlock:
        """
        Creates a MessageBlock directly from streaming event parameters.
        Ensures strict structural parity with from_orm.
        """
        metadata = metadata or {}

        # Resolve Input
        input_args = metadata.get("input", {})
        if not isinstance(input_args, dict):
            input_args = {}

        # Resolve Tool Meta (if missing, rebuild it)
        tool_meta = metadata.get("tool_meta")
        if not tool_meta and role == "tool" and tool_name:
            metadata_registry = get_tool_metadata(tool_name)

            # Try to extract result meta from content if role is tool and status is completed
            result_meta = {}
            output = content or metadata.get("output", "")
            if status == "completed" and isinstance(output, str) and output.strip().startswith("{"):
                try:
                    parsed = json.loads(output)
                    if isinstance(parsed, dict):
                        result_meta = {k.lower(): v for k, v in parsed.items()}
                except (json.JSONDecodeError, ValueError):
                    pass

            summary_args = {**input_args, **result_meta}
            display_name = metadata_registry.get_display_name(tool_name, summary_args)

            tool_meta = {
                "display_name": display_name,
                "affected_path_keys": metadata_registry.affected_path_keys,
            }

        # Build clean meta_data (exclude root fields to avoid duplication)
        clean_meta = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            **{k: v for k, v in metadata.items() if k not in ["input", "tool_meta"]},
        }

        if role == "tool":
            clean_meta["input"] = input_args
            clean_meta["tool_meta"] = tool_meta

        # Normalize tool_calls if present
        validated_tool_calls = None
        if tool_calls:
            validated_tool_calls = []
            for tc in normalize_tool_calls(tool_calls):
                validated_tool_calls.append(ToolCall(**tc))

        # Resolve References
        from app.core.engine.message.schemas import ReferenceBlock
        ref_blocks = []
        if references:
            for ref in references:
                if isinstance(ref, dict):
                    # Ensure metadata is mapped to meta_data for Pydantic schema validation
                    if "metadata" in ref and "meta_data" not in ref:
                        ref = {**ref, "meta_data": ref["metadata"]}
                    rb = ReferenceBlock(**ref)
                    ref_blocks.append(rb)
                elif isinstance(ref, ReferenceBlock):
                    ref_blocks.append(ref)

        return MessageBlock(
            id=message_id or f"msg-{thread_id}-{sequence_number}",
            thread_id=thread_id,
            run_id=run_id,
            role=role,  # type: ignore[arg-type]
            category=category,
            content=content or "",
            thinking=thinking,
            tool_calls=validated_tool_calls,
            references=ref_blocks,
            status=status,  # type: ignore[arg-type]
            is_visible=True,
            sequence_number=sequence_number,
            created_at=datetime.now().isoformat(),
            parent_id=parent_id,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            input=input_args if role == "tool" else None,
            tool_meta=tool_meta if role == "tool" else None,
            meta_data=clean_meta,
        )
