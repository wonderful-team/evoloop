"""
LLM Infrastructure Module

Provides LLM factory, adapters, and configuration services.
"""

from app.infrastructure.llm.factory import LLMFactory, get_default_llm
from app.infrastructure.llm.config import LLMConfigService
from app.infrastructure.llm.platform_service import (
    LLMPlatformService,
    llm_platform_service,
    get_available_llm_models,
    get_available_embedding_models,
    PlatformModel,
)
from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI

# Lazy import to avoid circular dependency
# CompatibleChatAnthropic imports from app.core.engine
# which may not be fully initialized during import
def __getattr__(name):
    if name == "CompatibleChatAnthropic":
        from app.infrastructure.llm.anthropic_adapter import CompatibleChatAnthropic
        return CompatibleChatAnthropic
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Factory
    "LLMFactory",
    "get_default_llm",
    # Config
    "LLMConfigService",
    # Platform Service
    "LLMPlatformService",
    "llm_platform_service",
    "get_available_llm_models",
    "get_available_embedding_models",
    "PlatformModel",
    # Adapters
    "AdaptiveChatOpenAI",
    "CompatibleChatAnthropic",
]
