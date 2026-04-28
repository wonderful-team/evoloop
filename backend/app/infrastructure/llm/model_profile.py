"""
Model Profile system for adaptive context management.

Provides model-specific parameters (context window, pruning thresholds, etc.)
to replace hardcoded constants throughout the system.
"""

import logging

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.infrastructure.schemas import ModelProfile

logger = logging.getLogger(__name__)

_BUILTIN_PROFILES: dict[str, ModelProfile] = {
    # OpenAI
    "gpt-4o": ModelProfile(
        name="gpt-4o",
        max_context_tokens=128000,
        recommended_output_tokens=4096,
        context_window_ratio=0.6,
        prune_threshold_ratio=0.7,
        truncate_limit_tokens=5000,
        supports_vision=True,
    ),
    "gpt-4o-mini": ModelProfile(
        name="gpt-4o-mini",
        max_context_tokens=128000,
        recommended_output_tokens=4096,
        context_window_ratio=0.6,
        prune_threshold_ratio=0.7,
        truncate_limit_tokens=5000,
        supports_vision=True,
    ),
    "gpt-4-turbo": ModelProfile(
        name="gpt-4-turbo",
        max_context_tokens=128000,
        recommended_output_tokens=4096,
        context_window_ratio=0.6,
        prune_threshold_ratio=0.7,
        truncate_limit_tokens=5000,
        supports_vision=True,
    ),
    "gpt-4": ModelProfile(
        name="gpt-4",
        max_context_tokens=8192,
        recommended_output_tokens=2048,
        context_window_ratio=0.65,
        prune_threshold_ratio=0.6,
        truncate_limit_tokens=2000,
        supports_vision=False,
    ),

    # Anthropic
    "claude-3-opus": ModelProfile(
        name="claude-3-opus",
        max_context_tokens=200000,
        recommended_output_tokens=4096,
        context_window_ratio=0.5,
        prune_threshold_ratio=0.8,
        truncate_limit_tokens=8000,
        supports_vision=True,
    ),
    "claude-3-sonnet": ModelProfile(
        name="claude-3-sonnet",
        max_context_tokens=200000,
        recommended_output_tokens=4096,
        context_window_ratio=0.5,
        prune_threshold_ratio=0.8,
        truncate_limit_tokens=8000,
        supports_vision=True,
    ),
    "claude-3.5-sonnet": ModelProfile(
        name="claude-3.5-sonnet",
        max_context_tokens=200000,
        recommended_output_tokens=8192,
        context_window_ratio=0.5,
        prune_threshold_ratio=0.8,
        truncate_limit_tokens=8000,
        supports_vision=True,
    ),
    "claude-3-haiku": ModelProfile(
        name="claude-3-haiku",
        max_context_tokens=200000,
        recommended_output_tokens=4096,
        context_window_ratio=0.5,
        prune_threshold_ratio=0.8,
        truncate_limit_tokens=6000,
        supports_vision=True,
    ),
    "claude-3.5-haiku": ModelProfile(
        name="claude-3.5-haiku",
        max_context_tokens=200000,
        recommended_output_tokens=8192,
        context_window_ratio=0.5,
        prune_threshold_ratio=0.8,
        truncate_limit_tokens=6000,
        supports_vision=True,
    ),

    # DeepSeek
    "deepseek-chat": ModelProfile(
        name="deepseek-chat",
        max_context_tokens=64000,
        recommended_output_tokens=4096,
        context_window_ratio=0.65,
        prune_threshold_ratio=0.65,
        truncate_limit_tokens=4000,
        supports_vision=False,
    ),
    "deepseek-v3": ModelProfile(
        name="deepseek-v3",
        max_context_tokens=64000,
        recommended_output_tokens=4096,
        context_window_ratio=0.65,
        prune_threshold_ratio=0.65,
        truncate_limit_tokens=4000,
        supports_vision=False,
    ),

    # Kimi / Moonshot
    "moonshot-v1-128k": ModelProfile(
        name="moonshot-v1-128k",
        max_context_tokens=128000,
        recommended_output_tokens=4096,
        context_window_ratio=0.6,
        prune_threshold_ratio=0.7,
        truncate_limit_tokens=5000,
        supports_vision=False,
    ),
    "kimi": ModelProfile(
        name="kimi",
        max_context_tokens=128000,
        recommended_output_tokens=4096,
        context_window_ratio=0.6,
        prune_threshold_ratio=0.7,
        truncate_limit_tokens=5000,
        supports_vision=False,
    ),

    # Zhipu / GLM
    "glm-4": ModelProfile(
        name="glm-4",
        max_context_tokens=128000,
        recommended_output_tokens=4096,
        context_window_ratio=0.6,
        prune_threshold_ratio=0.7,
        truncate_limit_tokens=5000,
        supports_vision=False,
    ),

    # Qwen
    "qwen-plus": ModelProfile(
        name="qwen-plus",
        max_context_tokens=131072,
        recommended_output_tokens=8192,
        context_window_ratio=0.55,
        prune_threshold_ratio=0.7,
        truncate_limit_tokens=5000,
        supports_vision=False,
    ),
    "qwen-max": ModelProfile(
        name="qwen-max",
        max_context_tokens=32768,
        recommended_output_tokens=4096,
        context_window_ratio=0.65,
        prune_threshold_ratio=0.65,
        truncate_limit_tokens=4000,
        supports_vision=False,
    ),
}

# Conservative default for unknown models
_DEFAULT_PROFILE = ModelProfile(
    name="unknown",
    max_context_tokens=32000,
    recommended_output_tokens=2048,
    context_window_ratio=0.6,
    prune_threshold_ratio=0.6,
    truncate_limit_tokens=3000,
    supports_vision=False,
)


def get_profile(model_name: str) -> ModelProfile:
    """
    Get the profile for a given model name.
    Supports fuzzy matching for versioned model names.
    
    Args:
        model_name: The model identifier (e.g. "gpt-4o-2024-05-13" or "custom-openai-gpt-4o")
    
    Returns:
        The matching ModelProfile, or a conservative default.
    """
    if not model_name:
        return _DEFAULT_PROFILE

    # Strip custom prefix if present: custom-{provider}-{actual_model}
    effective_name = model_name
    if model_name.startswith("custom-"):
        parts = model_name.split("-", 2)
        if len(parts) >= 3:
            effective_name = parts[2]

    # Exact match
    if effective_name in _BUILTIN_PROFILES:
        return _BUILTIN_PROFILES[effective_name]

    # Fuzzy match: try prefix matching
    model_lower = effective_name.lower()
    for known_name, profile in _BUILTIN_PROFILES.items():
        if model_lower.startswith(known_name):
            return profile

    logger.info(f"No model profile found for '{effective_name}' (from '{model_name}'), using conservative defaults.")
    return _DEFAULT_PROFILE


def get_current_profile() -> ModelProfile:
    """
    Get the profile for the currently configured LLM model.
    Reads from SystemConfigService (DB) -> Settings (env) fallback chain.
    """
    try:
        from app.infrastructure.config.service import SystemConfigService
        db_model = SystemConfigService.get_value("LLM_MODEL")
        if db_model:
            return get_profile(db_model)
    except Exception as e:
        logger.debug(f"Could not read model from SystemConfig: {e}")

    return _DEFAULT_PROFILE
