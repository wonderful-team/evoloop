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
    from app.core.llm import InternalLLMService
    from app.infrastructure.config.service import SystemConfigService

    model_name = SystemConfigService.get_value("LLM_MODEL")

    response = await InternalLLMService.invoke(
        messages=[
            {"role": "system", "content": "You are a memory selector."},
            {"role": "user", "content": prompt},
        ],
        purpose="memory_selection",  # 用于调试和追踪
        temperature=0.3,
        max_tokens=500,
        model_name=model_name,  # 必须显式传入，禁止隐式 fallback
    )

    content = response.content
"""

import logging
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


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
        **kwargs
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
            **kwargs: 其他参数传递给 LLM
            
        Returns:
            LLM 响应对象
            
        关键特性：
            - 自动禁用所有回调（config={"callbacks": []}）
            - 标记 metadata 表明是内部调用
            - 记录调用日志（仅用于调试，不存储消息）
        """
        from app.infrastructure.llm.factory import get_default_llm

        if not model_name:
            raise ValueError(
                "[InternalLLMService] No model specified. "
                "Please pass 'model_name' argument explicitly. "
                f"purpose={purpose}"
            )

        # 获取 LLM 实例
        llm = await get_default_llm(
            temperature=temperature,
            max_tokens=max_tokens,
            model_name=model_name,
        )

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
            logger.error(f"[InternalLLM] Failed for purpose '{purpose}': {e}")
            raise

    @staticmethod
    async def invoke_structured(
        messages: list[dict],
        output_schema: type[T],
        purpose: str,
        temperature: float = 0.3,
        max_tokens: int = 500,
        model_name: str | None = None,
        **kwargs
    ) -> T:
        """
        使用结构化输出模式调用 LLM
        """
        from app.infrastructure.llm.factory import get_default_llm

        if not model_name:
            raise ValueError(
                "[InternalLLMService] No model specified. "
                "Please pass 'model_name' argument explicitly. "
                f"purpose={purpose}"
            )

        llm = await get_default_llm(
            temperature=temperature,
            max_tokens=max_tokens,
            model_name=model_name,
        )

        # 绑定结构化输出
        structured_llm = llm.with_structured_output(output_schema)

        config = {
            "callbacks": [],
            "metadata": {
                "source": "internal_llm",
                "purpose": purpose,
                "output_schema": output_schema.__name__,
                "should_persist": False,
                "should_stream": False,
            },
        }

        logger.debug(
            f"[InternalLLM] Structured call: {purpose}, "
            f"schema: {output_schema.__name__}"
        )

        try:
            result = await structured_llm.ainvoke(messages, config=config)

            logger.debug(f"[InternalLLM] Structured completed: {purpose}")

            return result

        except Exception as e:
            logger.error(
                f"[InternalLLM] Structured failed for '{purpose}': {e}"
            )
            raise

    @staticmethod
    def validate_purpose(purpose: str) -> bool:
        """
        验证 purpose 是否有效
        
        有效的 purpose 应该：
        1. 使用小写字母和下划线
        2. 清晰描述调用用途
        3. 在已知列表中（可选）
        
        已知的 purpose 列表：
        - memory_selection: 记忆选择
        - memory_extraction: 记忆提取
        - task_decomposition: 任务分解
        - task_analysis: 任务分析
        - audit_summary: 审计总结
        - environment_triage: 环境探索
        - result_aggregation: 结果聚合
        - intent_matching: 意图匹配
        - vision_analysis: 视觉分析
        """
        import re

        # 格式验证：小写字母和下划线
        if not re.match(r'^[a-z_]+$', purpose):
            return False

        # 已知用途列表（可选验证）
        known_purposes = {
            "memory_selection",
            "memory_extraction",
            "task_decomposition",
            "task_analysis",
            "audit_summary",
            "environment_triage",
            "environment_exploration",
            "result_aggregation",
            "intent_matching",
            "intent_classification",
            "vision_analysis",
            "skill_discovery",
            "skill_matching",
        }

        # 如果不是已知用途，发出警告但不阻止
        if purpose not in known_purposes:
            logger.warning(
                f"[InternalLLM] Unknown purpose: {purpose}. "
                f"Consider adding it to the known purposes list."
            )

        return True
