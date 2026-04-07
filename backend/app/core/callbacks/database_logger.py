"""
DatabaseCallbackHandler - 数据库日志回调处理器（重构版）

使用 MessageHandler 架构，简化逻辑：
1. 所有消息分类由 MessageClassifier 处理
2. 持久化决策由 MessagePersistencePolicy 处理
3. 推送决策由 MessageStreamPolicy 处理

不再包含复杂的过滤逻辑！
"""

import logging
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.messaging import MessageHandler

logger = logging.getLogger(__name__)


class DatabaseCallbackHandler(AsyncCallbackHandler):
    """
    数据库日志回调处理器
    
    职责：
    1. 接收 LangChain 回调事件
    2. 提取消息数据
    3. 委托给 MessageHandler 处理
    
    注意：此处理器不再包含复杂的过滤逻辑！
    所有分类和策略决策都委托给 messaging 模块。
    """

    def __init__(
        self,
        thread_id: str,
        project_id: int,
        start_sequence: int = 0,
        run_id: str = None,
    ):
        self.thread_id = thread_id
        self.project_id = project_id
        self.run_id = run_id
        
        # 统一消息处理器
        self._handler = MessageHandler(
            thread_id=thread_id,
            project_id=project_id,
            run_id=run_id,
            start_sequence=start_sequence,
        )

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        """
        LLM 响应结束时调用
        
        处理 AI 消息：
        1. 提取内容和元数据
        2. 委托给 MessageHandler
        3. Handler 会自动分类并应用策略
        """
        try:
            if not response.generations:
                return

            generation = response.generations[0][0]
            message = generation.message
            
            # 提取内容
            content = self._extract_content(message.content)
            if not content:
                content = ""

            # 提取工具调用
            tool_calls = getattr(message, "tool_calls", None)
            
            # 提取元数据（可能包含 source 标记）
            metadata = getattr(message, "metadata", None)
            
            # 提取思考内容（从额外的 kwargs 或 content 中）
            thinking = self._extract_thinking(content)
            if thinking:
                # 移除思考标签后的内容
                content = self._remove_thinking_tags(content)

            # 委托给统一处理器
            # 所有分类和策略决策都在 handler 内部完成
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
            # 只记录错误，不抛出，避免影响主流程
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
        
        处理工具输出：
        1. 提取工具名称
        2. 委托给 MessageHandler
        """
        try:
            # 从 kwargs 中提取工具名称
            # LangChain 的 on_tool_end 会传递 name 参数
            tool_name = kwargs.get("name", "unknown_tool")
            
            # 委托给统一处理器
            result = await self._handler.handle_tool_output(
                tool_name=tool_name,
                output=output,
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

    def _extract_thinking(self, content: str) -> str | None:
        """提取思考内容（<think> 或 <audit> 标签）"""
        if not content:
            return None
        
        import re
        
        thinking_parts = []
        
        # 提取 <think> 内容
        think_match = re.search(
            r"<think>(.*?)</think>", 
            content, 
            re.DOTALL | re.IGNORECASE
        )
        if think_match:
            thinking_parts.append(think_match.group(1).strip())
        
        # 提取 <audit> 内容
        audit_match = re.search(
            r"<audit>(.*?)</audit>", 
            content, 
            re.DOTALL | re.IGNORECASE
        )
        if audit_match:
            thinking_parts.append(f"--- Audit ---\n{audit_match.group(1).strip()}")
        
        return "\n\n".join(thinking_parts) if thinking_parts else None

    def _remove_thinking_tags(self, content: str) -> str:
        """移除思考标签，保留其他内容"""
        if not content:
            return ""
        
        import re
        
        # 移除 <think> 标签
        content = re.sub(
            r"<think>.*?</think>", 
            "", 
            content, 
            flags=re.DOTALL | re.IGNORECASE
        )
        
        # 移除 <audit> 标签
        content = re.sub(
            r"<audit>.*?</audit>", 
            "", 
            content, 
            flags=re.DOTALL | re.IGNORECASE
        )
        
        # 清理空标签
        content = re.sub(r"<[^>]+>", "", content)
        
        return content.strip()

    # ========== 不需要处理的方法 ==========
    
    async def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        """流式 token，不需要处理"""
        pass

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> Any:
        """模型开始，不需要处理"""
        pass

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> Any:
        """工具开始，不需要处理（由 transparent handler 处理）"""
        pass

    async def on_tool_error(
        self,
        error: Exception,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> Any:
        """工具错误，记录日志即可"""
        logger.warning(f"[DatabaseCallback] Tool error: {error}")
