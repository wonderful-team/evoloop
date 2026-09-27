"""
InternalLLMService - 内部 LLM 调用服务

所有内部 LLM 调用的统一入口，特点：
1. 自动禁用所有回调（防止消息泄露到前端/数据库）
2. 标记调用来源（便于调试和追踪）
3. 统一的超时和重试机制
4. 类型安全的返回

使用场景：
- Memory 选择/提取
- Task 分解/分析
- 审计总结生成
- 环境探索
- 等等内部处理

使用示例：
    from app.infrastructure.llm import InternalLLMService

    response = await InternalLLMService.invoke(
        messages=[
            {"role": "system", "content": "You are a memory selector."},
            {"role": "user", "content": prompt},
        ],
        purpose="memory_selection",  # 用于调试和追踪
        temperature=0.3,
        max_tokens=500,
        # model_name 可选；不指定时由 LLMFactory.create_llm 统一解析默认模型
    )

    content = response.content
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class InternalLLMService:
    """
    内部 LLM 调用服务

    所有内部处理都应该使用此服务，而不是直接调用 LLM。
    这确保了内部处理不会意外触发回调，导致消息泄露。
    """

    @staticmethod
    async def invoke(
        messages: list[dict],
        purpose: str,
        temperature: float = 0.3,
        max_tokens: int = 500,
        model_name: str | None = None,
        extra_body: dict[str, Any] | None = None,
        **kwargs,
    ) -> Any:
        """
        调用 LLM 进行内部处理

        Args:
            messages: 消息列表，OpenAI 格式
            purpose: 调用用途，如 "memory_selection", "task_decomposition"
                    用于调试、追踪和日志记录
            temperature: 温度参数
            max_tokens: 最大 token 数
            model_name: 指定模型（可选，默认使用系统配置）
            extra_body: 附加请求体参数（可选），例如
                ``{"enable_thinking": False, "return_reasoning": False}``
                可对推理模型关闭思考。调用方覆盖默认 ThinkingConfig。
            **kwargs: 其他参数传递给 LLM

        Returns:
            LLM 响应对象

        关键特性：
            - 自动禁用所有回调（config={"callbacks": []}）
            - 标记 metadata 表明是内部调用
            - 记录调用日志（仅用于调试，不存储消息）
        """
        from app.infrastructure.llm.factory import get_default_llm

        # 获取 LLM 实例
        llm_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "model_name": model_name,
        }
        # 仅当调用方显式传了 extra_body 才透传（LLMConfig.extra_body 不接受 None）
        if extra_body is not None:
            llm_kwargs["extra_body"] = extra_body
        llm = await get_default_llm(**llm_kwargs)

        # 关键：禁用所有回调，防止消息泄露
        config = {
            "callbacks": [],  # 空列表 = 禁用所有回调
            "metadata": {
                "source": "internal_llm",
                "purpose": purpose,
                "should_persist": False,
                "should_stream": False,
            },
            **kwargs.get("config", {}),
        }

        # 记录内部调用（仅用于调试）
        logger.debug(
            f"[InternalLLM] Calling LLM for purpose: {purpose}, "
            f"messages: {len(messages)}, temp: {temperature}, max_tokens: {max_tokens}"
        )

        try:
            response = await llm.ainvoke(messages, config=config)

            logger.debug(f"[InternalLLM] Completed: {purpose}")

            return response

        except Exception as e:
            logger.exception(f"[InternalLLM] Failed for purpose '{purpose}': {e}")
            raise
