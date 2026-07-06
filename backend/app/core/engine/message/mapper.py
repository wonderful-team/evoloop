"""
BlockMapper —— 各层 ↔ MessageBlock 的标准化转换器。

职责：
1. DB ORM ↔ MessageBlock
2. Native BaseMessage ↔ MessageBlock
3. MessageBlock → SSE BlockEvent
4. MessageBlock → Mobile 推送字典

规则：
1. 所有转换必须是单向纯函数（无副作用）
2. 字段丢失必须显式标注（在注释中说明）
3. 不允许在转换中构造裸字典
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from app.models.schemas.events import MessageSyncEvent

from app.core.engine.message.native_classes import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from app.core.engine.message.reasoning import extract_reasoning_from_message
from app.core.engine.message.schemas import MessageBlock, ToolCall
from app.core.engine.message.utils import normalize_tool_calls

logger = logging.getLogger(__name__)


class BlockMapper:
    """标准化转换器：各层消息结构 ↔ MessageBlock"""

    # ------------------------------------------------------------------
    # DB ORM ↔ MessageBlock
    # ------------------------------------------------------------------

    @staticmethod
    def from_db(msg) -> MessageBlock:
        """数据库 Message ORM → MessageBlock"""
        from app.core.engine.message.schemas import MessageReference
        from app.models import Message as DBMessage

        if not isinstance(msg, DBMessage):
            raise TypeError(f"Expected DB Message, got {type(msg)}")

        # 1. 处理引用（标准化 MessageReference）
        references: list[MessageReference] = []

        # 变更集相关顶层字段
        has_file_ops = False
        changeset_count = 0
        changeset_files = []

        if msg.references:
            for ref in msg.references:
                msg_ref = MessageReference(
                    id=ref.id,
                    type=cast(Any, ref.type),
                    target_id=ref.target_id,
                    target_name=ref.target_name,
                    meta_data=ref.meta_data or {},
                )
                references.append(msg_ref)

                # 提取 changeset 数据到顶层
                if ref.type == "changeset":
                    has_file_ops = True
                    changeset_files = ref.meta_data.get("files", [])
                    changeset_count = ref.meta_data.get("count", len(changeset_files))

        # 2. 校验并归一化工具调用
        validated_tool_calls = None
        if msg.tool_calls:
            validated_tool_calls = []
            for tc in normalize_tool_calls(msg.tool_calls):
                validated_tool_calls.append(ToolCall(**tc))

        # 3. 提取工具元数据
        tool_meta = None
        if msg.meta_data and "tool_meta" in msg.meta_data:
            tool_meta = msg.meta_data["tool_meta"]

        return MessageBlock(
            id=str(msg.id),
            thread_id=msg.thread_id,
            run_id=msg.run_id,
            role=cast(Any, msg.role),
            category=msg.category or "",
            content_type=cast(Any, msg.content_type or "text"),
            content=msg.content or "",
            thinking=msg.thinking,
            tool_calls=validated_tool_calls,
            tool_name=msg.tool_name,
            tool_call_id=msg.tool_call_id,
            tool_meta=tool_meta,
            references=references,
            has_file_operations=has_file_ops,
            changeset_count=changeset_count,
            changeset_files=changeset_files,
            status=cast(Any, msg.status or "completed"),
            is_complete=msg.status == "completed",
            is_visible=msg.is_visible,
            created_at=_format_iso(msg.created_at),
            sequence_number=msg.sequence_number or 0,
            parent_id=str(msg.parent_id) if msg.parent_id else None,
            checkpoint_id=msg.checkpoint_id,
            meta_data=msg.meta_data or {},
        )

    @staticmethod
    def to_db(msg: MessageBlock) -> dict[str, Any]:
        """MessageBlock → 数据库 INSERT 字典（供 ORM 使用）"""
        return {
            "thread_id": msg.thread_id,
            "project_id": msg.meta_data.get("project_id"),
            "role": msg.role,
            "content": msg.content,
            "content_type": msg.content_type,
            "thinking": msg.thinking,
            "tool_calls": msg.tool_calls,
            "action_type": _infer_action_type(msg),
            "category": msg.category,
            "is_visible": msg.is_visible,
            "sequence_number": msg.sequence_number,
            "run_id": msg.run_id,
            "status": msg.status,
            "parent_id": msg.parent_id if msg.parent_id else None,
            "tool_call_id": msg.meta_data.get("tool_call_id"),
            "tool_name": msg.meta_data.get("tool_name"),
            "checkpoint_id": msg.checkpoint_id,
        }

    # ------------------------------------------------------------------
    # Native BaseMessage ↔ MessageBlock
    # ------------------------------------------------------------------

    @staticmethod
    def from_message(msg: BaseMessage) -> MessageBlock:
        """Native BaseMessage → MessageBlock"""
        kwargs: dict[str, Any] = {
            "id": _extract_lc_id(msg),
            "thinking": extract_reasoning_from_message(msg),
            "created_at": _format_iso(msg.additional_kwargs.get("created_at")),
            "thread_id": msg.additional_kwargs.get("thread_id", ""),
            "run_id": msg.additional_kwargs.get("run_id"),
            "category": msg.additional_kwargs.get("category", ""),
            "sequence_number": msg.additional_kwargs.get("sequence_number", 0),
            "content_type": msg.additional_kwargs.get("content_type", "text"),
            "checkpoint_id": msg.additional_kwargs.get("checkpoint_id"),
        }

        if isinstance(msg, AIMessage):
            validated_tool_calls: list[ToolCall] | None = None
            if msg.tool_calls:
                validated_tool_calls = []
                for tc in normalize_tool_calls(msg.tool_calls):
                    validated_tool_calls.append(ToolCall(**tc))

            return MessageBlock(
                role="ai",
                content=str(msg.content or ""),
                tool_calls=validated_tool_calls,
                status="completed",
                **kwargs,
            )

        elif isinstance(msg, ToolMessage):
            return MessageBlock(
                role="tool",
                content=str(msg.content or ""),
                status="completed",
                meta_data={
                    "tool_call_id": msg.tool_call_id or "",
                    "tool_name": msg.name or "",
                },
                **kwargs,
            )

        elif isinstance(msg, HumanMessage):
            return MessageBlock(
                role="human",
                content=str(msg.content or ""),
                status="completed",
                **kwargs,
            )

        elif isinstance(msg, SystemMessage):
            return MessageBlock(
                role="system",
                content=str(msg.content or ""),
                status="completed",
                **kwargs,
            )

        else:
            raise ValueError(f"Unsupported message type: {type(msg)}")

    @staticmethod
    def to_message(msg: MessageBlock) -> BaseMessage:
        """MessageBlock → native BaseMessage（用于 LLM 推理）"""
        kwargs: dict[str, Any] = {
            "id": msg.id,
            "additional_kwargs": {
                "created_at": msg.created_at,
                "thinking": msg.thinking,
                "thread_id": msg.thread_id,
                "run_id": msg.run_id,
                "category": msg.category,
                "sequence_number": msg.sequence_number,
                "content_type": msg.content_type,
                "checkpoint_id": msg.checkpoint_id,
                "references": [ref.model_dump() for ref in msg.references]
                if msg.references
                else None,
            },
        }

        if msg.role == "ai":
            return AIMessage(
                content=msg.content,
                tool_calls=msg.tool_calls or [],
                **kwargs,
            )
        elif msg.role == "tool":
            return ToolMessage(
                content=msg.content,
                tool_call_id=msg.meta_data.get("tool_call_id", ""),
                name=msg.meta_data.get("tool_name", ""),
                **kwargs,
            )
        elif msg.role == "human":
            return HumanMessage(content=msg.content, **kwargs)
        elif msg.role == "system":
            return SystemMessage(content=msg.content, **kwargs)
        else:
            raise ValueError(f"Unknown role: {msg.role}")

    # ------------------------------------------------------------------
    # MessageBlock → 各通道格式
    # ------------------------------------------------------------------

    @staticmethod
    def to_sse(msg: MessageBlock, action: str = "create") -> "MessageSyncEvent":
        """MessageBlock → SSE 流式事件（使用统一协议）"""
        from app.models.schemas.events import MessageSyncEvent

        return MessageSyncEvent(
            thread_id=msg.thread_id,
            action=cast(Any, action),
            data=msg,
        )

    @staticmethod
    def to_mobile(msg: MessageBlock) -> dict[str, Any]:
        """
        MessageBlock → Mobile 推送字典。

        字段名保持与 MessageBlock 一致，仅做格式兼容转换：
        - created_at: ISO 字符串 → Unix 秒级整数
        - is_visible: bool → int (0/1)
        """
        # Defensive: ensure tool_calls are pure dicts before serialization
        safe_msg = msg.model_copy(deep=True)
        if safe_msg.tool_calls:
            safe_tool_calls: list[dict[str, Any]] = []
            for tc in safe_msg.tool_calls:
                if hasattr(tc, "model_dump"):
                    safe_tool_calls.append(tc.model_dump())
                elif isinstance(tc, dict):
                    safe_tool_calls.append(tc)
                else:
                    safe_tool_calls.append(
                        {"id": str(tc), "type": str(type(tc).__name__)}
                    )
            safe_msg.tool_calls = cast(Any, safe_tool_calls)

        data = safe_msg.model_dump(exclude_none=True)

        # Mobile 兼容：created_at 从 ISO 字符串转 Unix 秒级
        if msg.created_at:
            try:
                dt = datetime.fromisoformat(msg.created_at.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                data["created_at"] = int(dt.timestamp())
            except (ValueError, TypeError):
                data["created_at"] = 0

        # Mobile 兼容：is_visible bool → int
        data["is_visible"] = 1 if msg.is_visible else 0

        data["source"] = msg.source

        # 节省带宽：Mobile 不需要 thinking 过程和原始元数据
        data.pop("thinking", None)
        data.pop("meta_data", None)

        if msg.role == "human" and msg.id:
            data["client_message_id"] = msg.id

        return data


# ----------------------------------------------------------------------
# 内部辅助函数
# ----------------------------------------------------------------------


def _extract_lc_id(msg: BaseMessage) -> str:
    """从消息中提取或生成 ID"""
    return msg.id or msg.additional_kwargs.get("id") or f"lc-{id(msg)}"


def _format_iso(dt: datetime | str | None) -> str:
    """统一时间戳格式为 ISO 8601"""
    if not dt:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _infer_action_type(msg: MessageBlock) -> str:
    """从 MessageBlock 推断 action_type（兼容旧系统）"""
    if msg.thinking and not msg.content:
        return "thinking"
    if msg.role == "tool":
        return "tool_output"
    return "text"
