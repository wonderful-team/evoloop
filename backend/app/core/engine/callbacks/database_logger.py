"""
DatabaseCallbackHandler - 数据库日志回调处理器（重构版）

使用 MessageHandler 架构，简化逻辑：
1. 所有消息分类由 MessageClassifier 处理
2. 持久化决策由 MessagePersistencePolicy 处理
3. 推送决策由 MessageStreamPolicy 处理

不再包含复杂的过滤逻辑！
"""

import logging
import re
from typing import Any
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
        self._tool_info_by_run_id: dict[str, dict[str, str]] = {}

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
            elif hasattr(message, "additional_kwargs") and message.additional_kwargs:
                tool_calls = message.additional_kwargs.get("tool_calls")

            # 提取元数据
            metadata = getattr(message, "metadata", None) or {}

            # 提取思考内容
            # 优先从 additional_kwargs 读取原生 reasoning_content (kimi-k2-thinking-turbo)
            additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
            thinking = self._extract_thinking(content, additional_kwargs)
            if thinking:
                content = self._remove_thinking_tags(content, additional_kwargs)
            # 确保 metadata 传递 reasoning_content 信息，供 handler 正确标记 thinking_type
            if additional_kwargs.get("reasoning_content"):
                metadata = {**metadata, "reasoning_content": additional_kwargs["reasoning_content"]}

            # 委托给统一处理器
            result = await self._handler.handle_ai_message(
                content=content,
                tool_calls=tool_calls,
                thinking=thinking,
                metadata=metadata,
            )

            logger.debug(
                f"[DatabaseCallback] AI message handled: "
                f"category={result['category']}, "
                f"persisted={result['persisted']}, "
                f"streamed={result['streamed']}"
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

            if not tool_name:
                # 回退逻辑
                tool_name = 'unknown_tool'
                tool_call_id = run_id_str # 假设 run_id 就是 tool_call_id（符合 Engine 行为）

            # 委托给统一处理器
            result = await self._handler.handle_tool_output(
                tool_name=tool_name,
                output=output,
                tool_call_id=tool_call_id,
            )

            logger.debug(
                f"[DatabaseCallback] Tool output handled: "
                f"tool={tool_name}, "
                f"category={result['category']}, "
                f"persisted={result['persisted']}"
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

    def _extract_thinking(self, content: str, additional_kwargs: dict | None = None) -> str | None:
        """提取思考内容 — 仅支持原生 reasoning_content。"""
        return extract_reasoning_from_kwargs(additional_kwargs)

    def _remove_thinking_tags(self, content: str, additional_kwargs: dict | None = None) -> str:
        """移除思考标签，保留其他内容。

        Native reasoning_content flows outside content, so no tags to strip.
        Only <evoloop_session_audit> hidden tags may remain (filtered by TokenFilter
        during streaming, but present in final content from some providers).
        """
        if not content:
            return ""

        # Native reasoning_content: content is already clean
        if additional_kwargs and additional_kwargs.get("reasoning_content"):
            return content.strip()

        # Defensive: strip any leftover hidden audit tags
        content = re.sub(
            r"<evoloop_session_audit>.*?</evoloop_session_audit>",
            "",
            content,
            flags=re.DOTALL | re.IGNORECASE
        )

        return content.strip()

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> Any:
        """
        工具执行开始时调用
        """
        try:
            # 提取工具名称
            tool_name = serialized.get("name") if serialized else "unknown_tool"
            run_id_str = str(run_id)
            tool_call_id = kwargs.get("tool_call_id") or run_id_str

            # 存储工具详情（支持并行工具）
            self._tool_info_by_run_id[run_id_str] = {
                "name": tool_name,
                "tool_call_id": tool_call_id
            }
            self._current_tool_name = tool_name

            logger.debug(f"[DatabaseCallback] Tool started: {tool_name} (tool_call_id={tool_call_id})")
        except Exception as e:
            logger.debug(f"[DatabaseCallback] Failed to track tool start: {e}")

    async def on_tool_error(
        self,
        error: Exception,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> Any:
        """工具错误，记录日志即可"""
        logger.warning(f"[DatabaseCallback] Tool error: {error}")
