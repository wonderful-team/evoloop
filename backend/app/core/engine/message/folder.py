"""
MessageFolder - 消息折叠工具类

统一处理消息由扁平结构向嵌套结构（FoldedMessage/ToolStep）的转换逻辑。
解决流式推送与历史加载逻辑不一致的问题。
"""
import logging
import time
from datetime import datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.core.engine.reasoning import extract_reasoning_from_message
from app.core.engine.state.history import FoldedMessage, ToolStep
from app.core.tools.registry import get_tool_friendly_name, get_tool_metadata
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
    def append_tool_event_to_ai_message(ai_message: dict, tool_event: dict) -> None:
        """
        Append a tool execution event to its parent AI message's steps array.
        Used by the real-time SSE stream to fold tool messages on the fly.
        """
        tool_id = tool_event.get('tool_call_id')
        tool_name = tool_event.get('tool_name') or 'unknown'
        tool_name_display = tool_event.get('tool_name_display') or None
        
        # Find matching tool call in the parent AI message
        tool_calls = ai_message.get('tool_calls', []) or []
        matched_call = next((tc for tc in tool_calls if tc.get('id') == tool_id), None)
        
        tool_input = matched_call.get('args', {}) if matched_call else {}
        
        step = ToolStep(
            id=tool_event.get('id') or f"step-{time.monotonic()}",
            tool=tool_name,
            tool_name=tool_name,
            tool_name_display=tool_name_display,
            input=tool_input,
            output=tool_event.get('content', ''),
            status='success',
            tool_call_id=tool_id,
        )
        
        if 'steps' not in ai_message:
            ai_message['steps'] = []
            
        # Avoid duplicate steps if event is re-sent
        # Guard: only deduplicate when both IDs are non-None to prevent
        # false collisions between unrelated steps that both lack an ID.
        if tool_id is not None:
            if not any(s.get('tool_call_id') == tool_id for s in ai_message['steps']):
                ai_message['steps'].append(step.model_dump())
        else:
            ai_message['steps'].append(step.model_dump())

    @staticmethod
    def _build_tool_name_display(tool_name: str, args: dict | None, lang: str = "zh") -> str | None:
        """
        使用与 TransparentCallback 相同的 i18n 模板生成带参数的友好名称。
        例如: read_file + {path: '/foo.py'} → "正在读取 '/foo.py'"
        """
        if not args:
            return None
        metadata = get_tool_metadata(tool_name) or {}
        summary_template = metadata.get("summary_template")
        if not summary_template:
            return None
        try:
            return i18n.get(summary_template, **args)
        except (KeyError, TypeError):
            return None

    @staticmethod
    def to_tool_step(
        tool_msg: ToolMessage, 
        tc_name: str | None = None, 
        tc_args: dict | None = None,
        lang: str = "zh"
    ) -> ToolStep:
        """
        将单条 ToolMessage 转换为 ToolStep 结构
        
        Args:
            tool_msg: 工具返回的消息
            tc_name: 对应的工具调用名称（若无法从 msg 自动获取则手动传入）
            tc_args: 对应的工具调用参数
            lang: 语言偏好，用于友好名称解析
        """
        tool_id = tool_msg.tool_call_id or gen_uuid()
        tool_name_raw = tool_msg.name or tc_name or "unknown"
        args = tc_args or {}
        
        # 通用友好名称 (e.g. "正在读取文件")
        friendly_name = get_tool_friendly_name(tool_name_raw, lang=lang) or tool_name_raw
        
        # 带参数的显示名 (e.g. "正在读取 '/path/to/file'")
        tool_name_display = MessageFolder._build_tool_name_display(tool_name_raw, args, lang)

        return ToolStep(
            id=tool_id,
            tool=tool_name_raw,
            tool_name=friendly_name,
            tool_name_display=tool_name_display,
            input=args,
            output=MessageFolder.get_message_text(tool_msg),
            status="success",
            tool_call_id=tool_msg.tool_call_id
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
            msg_id = getattr(msg, "id", None) or msg.additional_kwargs.get("id") or f"msg-{i}"
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

                # 向后扫描 ToolMessages
                j = i + 1
                while j < len(messages) and isinstance(messages[j], ToolMessage):
                    tool_msg = messages[j]
                    
                    # 匹配逻辑：优先 ID，次选顺序与名称
                    matched_tc = next((tc for tc in current_turn_tcs if tc['id'] == tool_msg.tool_call_id), None)
                    if not matched_tc:
                        matched_tc = next((tc for tc in current_turn_tcs if not tc['matched'] and tc['name'] == tool_msg.name), None)

                    if matched_tc:
                        matched_tc['matched'] = True
                        tc_info = matched_tc['raw']
                        tc_name = tc_info.get("name") if isinstance(tc_info, dict) else getattr(tc_info, "name", "unknown")
                        tc_args = tc_info.get("args") if isinstance(tc_info, dict) else getattr(tc_info, "args", {})
                    else:
                        tc_name = tool_msg.name or "unknown"
                        tc_args = {}

                    steps.append(cls.to_tool_step(tool_msg, tc_name=tc_name, tc_args=tc_args, lang=lang))
                    j += 1

                # 读取原生 reasoning_content
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
                i = j

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
