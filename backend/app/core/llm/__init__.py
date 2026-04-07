"""
EvoLoop LLM Services - LLM 服务模块

提供不同类型的 LLM 调用服务：
- InternalLLMService: 内部处理调用（不触发回调，不入库）
- 未来可扩展：StreamingLLMService, StructuredLLMService 等
"""

from app.core.llm.internal_service import InternalLLMService

__all__ = ["InternalLLMService"]
