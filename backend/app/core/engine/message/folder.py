"""
MessageFolder - 消息折叠工具类

统一处理消息由扁平结构向嵌套结构（FoldedMessage/ToolStep）的转换逻辑。
解决流式推送与历史加载逻辑不一致的问题。
"""
import logging
import time
from datetime import datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.core.engine.message.reasoning import extract_reasoning_from_message
from app.core.engine.state.history import FoldedMessage, ToolStep
from app.core.tools.registry import get_tool_metadata
from app.i18n.service import i18n
from app.utils import gen_uuid

logger = logging.getLogger(__name__)


class MessageFolder:
    """
    消息折叠工具集
    """

    @staticmethod
    def get_message_text(message: BaseMessage | str) -> str:
        """从消息对象中提取文本内容"""
        if isinstance(message, str):
            return message

        content = message.content
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
            return "\n".join(text_parts)

        return ""

    @staticmethod
    def append_tool_event_to_ai_message(
        ai_message: dict, tool_event: dict, status: str = "done"
    ) -> None:
        """
        Append or update a tool execution event in its parent AI message's steps array.
        Used by the real-time SSE stream to fold tool messages on the fly.

        Args:
            ai_message: The parent AI message dict (mutated in place).
            tool_event: The tool event dict from MessageBlock dispatch.
            status: ToolStep status — "running" on start, "done" on success, "failed" on error.
        """
        tool_id = tool_event.get('tool_call_id')
        tool_name = (
            tool_event.get('tool_name')
            or tool_event.get('metadata', {}).get('tool_name')
            or 'unknown'
        )
        tool_meta = tool_event.get('metadata', {}).get('tool_meta', {})
        tool_input = tool_event.get('metadata', {}).get('input', {})

        if 'steps' not in ai_message:
            ai_message['steps'] = []

        steps: list[dict] = ai_message['steps']

        # Try to find existing step by tool_call_id for update
        existing_idx = next(
            (i for i, s in enumerate(steps) if s.get('tool_call_id') == tool_id and tool_id is not None),
            -1,
        )

        if existing_idx >= 0:
            # Update existing step — preserve name/input from create event
            existing = steps[existing_idx]
            existing['status'] = status
            existing['output'] = tool_event.get('content', '')
            if tool_meta:
                existing['tool_meta'] = tool_meta
        else:
            # Create new step
            step = ToolStep(
                id=tool_id or f"step-{time.monotonic()}",
                tool=tool_name,
                name=tool_meta.get('display_name') or tool_name,
                input=tool_input,
                output=tool_event.get('content', ''),
                status=status,
                tool_call_id=tool_id,
                tool_meta=tool_meta,
            )
            steps.append(step.model_dump())

    @staticmethod
    def to_tool_step(
        tool_msg: ToolMessage, 
        tc_id: str | None = None,
        tc_name: str | None = None, 
        tc_args: dict | None = None,
        lang: str = "zh"
    ) -> ToolStep:
        """
        将单条 ToolMessage 转换为 ToolStep 结构
        
        Args:
            tool_msg: 工具返回的消息
            tc_id: 显式的工具调用 ID
            tc_name: 对应的工具调用名称
            tc_args: 对应的工具调用参数
            lang: 语言偏好
        """
        tool_id = tc_id or tool_msg.tool_call_id or gen_uuid()
        tool_name_raw = tool_msg.name or tc_name or "unknown"
        args = tc_args or {}
        
        # Build tool_meta for backend-driven rendering
        metadata = get_tool_metadata(tool_name_raw) or {}
        summary_template = metadata.get("summary_template")
        tool_name_display = None
        
        if summary_template:
            try:
                # Always attempt to get translation, even if args is empty.
                # i18n.get handles missing placeholders gracefully by returning the template.
                tool_name_display = i18n.get(summary_template, **args)
            except Exception:
                pass

        # Fallback: if no display name from i18n, use Title Case of the raw tool name
        if not tool_name_display or tool_name_display == summary_template:
            tool_name_display = tool_name_raw.replace("_", " ").title()

        tool_meta = {
            "affected_path_keys": metadata.get("affected_path_keys", []),
            "display_name": tool_name_display,
        }

        # Use status from message metadata (additional_kwargs) or default to 'done'
        status = tool_msg.additional_kwargs.get("status", "done")

        return ToolStep(
            id=tool_id,
            tool=tool_name_raw,
            name=tool_meta.get('display_name') or tool_name_raw,
            input=args,
            output=MessageFolder.get_message_text(tool_msg),
            status=status,
            tool_call_id=tool_msg.tool_call_id,
            tool_meta=tool_meta,
        )

    @classmethod
    def fold(cls, messages: list[BaseMessage], lang: str = "zh") -> list[FoldedMessage]:
        """
        将扁平的消息列表折叠为嵌套结构
        """
        result: list[FoldedMessage] = []
        i = 0

        while i < len(messages):
            msg = messages[i]

            # 获取统一 ID 和时间戳
            msg_id = msg.id or msg.additional_kwargs.get("id") or f"msg-{i}"
            created_at = getattr(msg, "created_at", None) or msg.additional_kwargs.get("created_at")
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()

            # --- 动态扫描与匹配 ---
            if isinstance(msg, AIMessage):
                steps = []
                tool_calls = msg.tool_calls or []
                
                # 建立当前轮次的工具调用索引
                current_turn_tcs = []
                for tc in tool_calls:
                    tc_id = tc['id'] if isinstance(tc, dict) else tc.id
                    tc_name = tc.get('name') if isinstance(tc, dict) else getattr(tc, 'name', '')
                    current_turn_tcs.append({'id': tc_id, 'name': tc_name, 'raw': tc, 'matched': False})

                # 向后扫描 ToolMessages 并进行去重合并
                j = i + 1
                step_map: dict[str, ToolStep] = {}
                while j < len(messages) and isinstance(messages[j], ToolMessage):
                    tool_msg = messages[j]
                    
                    # 匹配逻辑：优先 ID，次选名称（允许同一工具定义被多次匹配以支持状态更新合并）
                    matched_tc = next((tc for tc in current_turn_tcs if tc['id'] == tool_msg.tool_call_id and tool_msg.tool_call_id), None)
                    if not matched_tc:
                        matched_tc = next((tc for tc in current_turn_tcs if tc['name'] == tool_msg.name), None)

                    if matched_tc:
                        matched_tc['matched'] = True
                        tc_info = matched_tc['raw']
                        tc_id = matched_tc['id']
                        tc_name = tc_info.get("name") if isinstance(tc_info, dict) else getattr(tc_info, "name", "unknown")
                        tc_args = tc_info.get("args") if isinstance(tc_info, dict) else getattr(tc_info, "args", {})
                    else:
                        tc_id = tool_msg.tool_call_id
                        tc_name = tool_msg.name or "unknown"
                        tc_args = {}

                    new_step = cls.to_tool_step(tool_msg, tc_id=tc_id, tc_name=tc_name, tc_args=tc_args, lang=lang)
                    tcid = new_step.tool_call_id or new_step.id

                    if tcid in step_map:
                        # 合并逻辑：如果新步骤有结果或状态是完成/失败，则覆盖旧的 running 状态
                        existing = step_map[tcid]
                        if new_step.status in ["completed", "done", "failed"] or existing.status == "running":
                            existing.status = new_step.status
                            existing.output = new_step.output
                    else:
                        step_map[tcid] = new_step
                    j += 1

                steps = list(step_map.values())

                thinking_content = extract_reasoning_from_message(msg)

                result.append(FoldedMessage(
                    id=msg_id,
                    role="ai",
                    content=cls.get_message_text(msg),
                    thinking=thinking_content,
                    tool_calls=[(tc.model_dump() if hasattr(tc, 'model_dump') else tc) for tc in tool_calls] if tool_calls else None,
                    steps=steps,
                    created_at=created_at
                ))
                # Move to next message without skipping the tool messages we just scanned.
                # This ensures they still appear as independent entries in the main chat.
                i += 1

            elif isinstance(msg, ToolMessage):
                # 孤立的工具消息
                result.append(FoldedMessage(
                    id=f"orphan-{msg.tool_call_id}",
                    role="tool",
                    content=cls.get_message_text(msg),
                    metadata={"tool": msg.name or "unknown", "tool_call_id": msg.tool_call_id, "orphan": True}
                ))
                i += 1
            elif isinstance(msg, HumanMessage):
                result.append(FoldedMessage(id=msg_id, role="human", content=cls.get_message_text(msg), created_at=created_at))
                i += 1
            elif isinstance(msg, SystemMessage):
                result.append(FoldedMessage(id=f"system-{i}", role="system", content=cls.get_message_text(msg)))
                i += 1
            else:
                i += 1

        return result
