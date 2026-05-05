"""
DatabaseCallbackHandler - 数据库日志回调处理器（重构版）

使用 MessageHandler 架构，简化逻辑：
1. 所有消息分类由 MessageClassifier 处理
2. 持久化决策由 MessagePersistencePolicy 处理
3. 推送决策由 MessageStreamPolicy 处理

不再包含复杂的过滤逻辑！
"""
import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.engine.message import MessageHandler
from app.core.engine.message.reasoning import extract_reasoning_from_kwargs

logger = logging.getLogger(__name__)


class DatabaseCallbackHandler(AsyncCallbackHandler):
    """
    数据库日志回调处理器
    
    职责：
    1. 接收 LangChain 回调事件
    2. 提取消息数据
    3. 委托给 MessageHandler 处理
    
    注意：此处理器不再包含复杂的过滤逻辑！
    所有分类和策略决策都委托给 message 模块。
    """

    def __init__(self, thread_id: str, project_id: int, run_id: str = None):
        self.thread_id = thread_id
        self.project_id = project_id
        self.run_id = run_id

        # 统一消息处理器
        self._handler = MessageHandler(
            thread_id=thread_id,
            project_id=project_id,
            run_id=run_id,
        )

        # 步骤追踪（用于与 activity_monitor 协调）
        self._last_attributed_step_index: int = 0

        # 当前工具名称追踪（LangChain on_tool_end 不传递 name，需要在 on_tool_start 存储）
        self._tool_info_by_run_id: dict[str, dict[str, Any]] = {}

        # 消息父子关系追踪
        self._last_ai_message_id: str | None = None

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        """
        LLM 响应结束时调用
        
        处理 AI 消息：
        1. 提取内容和元数据
        2. 委托给 MessageHandler
        3. Handler 会自动分类并应用策略
        """
        if not response.generations:
            return

        try:
            generation = response.generations[0][0]
            message = generation.message

            # 提取内容
            content = self._extract_content(message.content)
            if not content:
                content = ""

            # 提取工具调用
            tool_calls = None
            if hasattr(message, "tool_calls") and message.tool_calls:
                tool_calls = message.tool_calls
            elif message.additional_kwargs:
                tool_calls = message.additional_kwargs.get("tool_calls")

            # 提取元数据
            metadata = getattr(message, "metadata", None) or {}

            # 提取思考内容（native reasoning_content）
            additional_kwargs = message.additional_kwargs or {}
            thinking = extract_reasoning_from_kwargs(additional_kwargs)
            # 传递 reasoning_content 信息，供 handler 正确标记 thinking_type
            if additional_kwargs.get("reasoning_content"):
                metadata = {**metadata, "reasoning_content": additional_kwargs["reasoning_content"]}

            # 委托给统一处理器
            result = await self._handler.handle_ai_message(
                content=content,
                tool_calls=tool_calls,
                thinking=thinking,
                metadata=metadata,
                parent_id=None, # AI messages usually parents of previous turn's last message (resolved in repo)
            )

            # Store the message_id for subsequent tools/HITL in this turn
            if result.message_id:
                self._last_ai_message_id = result.message_id
                from app.core.context.manager import ContextManager
                try:
                    ctx = ContextManager.current()
                    ctx.last_ai_message_id = result.message_id
                except Exception:
                    pass

            # 重要：将持久化后的 ID 和序列号回填给消息对象，供后续环节（如 MemoryExtractor）使用
            if result.get("message_id"):
                message.id = str(result["message_id"])
                # 同时回填 sequence_number 到 additional_kwargs，确保 ID 构造的一致性
                if message.additional_kwargs is None:
                    message.additional_kwargs = {}
                message.additional_kwargs["sequence_number"] = result.get("sequence_number", 0)

            logger.debug(
                f"[DatabaseCallback] AI message handled: "
                f"category={result['category']}, "
                f"persisted={result['persisted']}, "
                f"id={message.id}, seq={result.get('sequence_number')}"
            )

        except Exception as e:
            logger.error(f"[DatabaseCallback] Failed to handle AI message: {e}")

    async def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        工具执行结束时调用
        """
        try:
            run_id_str = str(run_id)

            # 从存储的映射中获取工具信息
            tool_info = self._tool_info_by_run_id.pop(run_id_str, {})
            tool_name = tool_info.get("name")
            tool_call_id = tool_info.get("tool_call_id")
            seq = tool_info.get("seq")

            if not tool_name:
                # 回退逻辑
                tool_name = 'unknown_tool'
                tool_call_id = run_id_str # 假设 run_id 就是 tool_call_id（符合 Engine 行为）

            # 委托给统一处理器，传入 sequence_number 以 UPDATE 记录
            result = await self._handler.handle_tool_output(
                tool_name=tool_name,
                output=output,
                tool_call_id=tool_call_id,
                sequence_number=seq,
            )

            # 注意：on_tool_end 并不直接持有 ToolMessage 对象，因此无法直接回填 ID。
            # 但由于 handle_tool_output 内部使用了 deduplicator，重复调用会被拦截。
            # 此外，FinishNode 的增量过滤逻辑也会基于内容进行防御。

            logger.debug(
                f"[DatabaseCallback] Tool output handled: "
                f"tool={tool_name}, "
                f"category={result['category']}, "
                f"persisted={result['persisted']}, "
                f"id={result.get('message_id')}"
            )

        except Exception as e:
            logger.error(f"[DatabaseCallback] Failed to handle tool output: {e}")

    def _extract_content(self, content: Any) -> str:
        """提取文本内容，处理多模态格式"""
        if not content:
            return ""

        # 处理列表格式（Anthropic/Zhipu 结构化输出）
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)
            return "".join(text_parts)

        return str(content)

    async def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """
        工具执行开始时调用 — 预插入 running 状态记录
        """
        try:
            # 提取工具名称
            tool_name = serialized.get("name") if serialized else "unknown_tool"
            run_id_str = str(run_id)
            
            # 使用传入的 metadata 参数，而不是从 kwargs 中提取（因为它已被参数捕获）
            effective_metadata = metadata or {}
            tool_call_id = (
                effective_metadata.get("_evoloop_tool_call_id") or 
                kwargs.get("tool_call_id")
            )

            # Parse input data
            from app.core.engine.message.utils import parse_tool_input
            input_data = parse_tool_input(input_str)

            # Pre-insert running record via MessageHandler
            result = await self._handler.handle_tool_start(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                input_data=input_data,
                parent_id=self._last_ai_message_id,
            )

            # Store in context for HITL tools to access
            from app.core.context.manager import ContextManager
            ctx = ContextManager.current()
            ctx.current_tool_call_id = tool_call_id

            # 存储工具详情（支持并行工具）
            self._tool_info_by_run_id[run_id_str] = {
                "name": tool_name,
                "tool_call_id": tool_call_id,
                "seq": result.sequence_number,
            }

            logger.debug(f"[DatabaseCallback] Tool started: {tool_name} (tool_call_id={tool_call_id}, seq={result.sequence_number})")
        except Exception as e:
            logger.debug(f"[DatabaseCallback] Failed to track tool start: {e}")

    async def on_tool_error(
        self,
        error: Exception,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> Any:
        """工具错误 — 将 running 记录标记为 failed"""
        run_id_str = str(run_id)
        tool_info = self._tool_info_by_run_id.pop(run_id_str, {})
        tool_name = tool_info.get("name", "unknown_tool")
        tool_call_id = tool_info.get("tool_call_id", run_id_str)
        seq = tool_info.get("seq")

        try:
            await self._handler.handle_tool_error(
                tool_name=tool_name,
                error=error,
                tool_call_id=tool_call_id,
                sequence_number=seq,
            )
            logger.debug(f"[DatabaseCallback] Tool error tracked: {tool_name} (seq={seq})")
        except Exception as e:
            logger.debug(f"[DatabaseCallback] Failed to track tool error: {e}")
