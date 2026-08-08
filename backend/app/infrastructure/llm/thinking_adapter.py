"""
Thinking Budget Adapter
将 ThinkingConfig 的语义意图翻译为各 LLM Provider 的原生参数格式。
每个函数都是纯函数，无副作用，便于单元测试。
"""

from __future__ import annotations

from typing import Any

from app.infrastructure.schemas import ThinkingConfig

# --- 模型族检测 ---


def detect_model_family(model_name: str, base_url: str = "") -> str:
    """
    返回: "anthropic" | "openai_reasoning" | "openai_compat"
    其余厂商（glm/qwen/kimi/minimax/gemini 等）统一按 OpenAI 兼容处理。
    """
    n = model_name.lower()
    u = (base_url or "").lower()
    if "claude" in n or "anthropic" in u:
        return "anthropic"
    if any(n.startswith(p) for p in ("o1", "o3", "o4")):
        return "openai_reasoning"
    return "openai_compat"


# --- Anthropic ---


def build_anthropic_thinking_kwargs(cfg: ThinkingConfig) -> dict[str, Any]:
    """
    返回 Anthropic model_kwargs 中的 thinking 参数。
    使用新版 adaptive API（已废弃 budget_tokens）。
    旧版: {"type": "enabled", "budget_tokens": N}
    新版: {"type": "adaptive", "effort": "high"}  ← 使用此格式
    """
    if not cfg.enable:
        return {}
    effort = cfg.reasoning_effort or "high"
    return {"thinking": {"type": "adaptive", "effort": effort}}


# --- OpenAI o 系列 ---


def build_openai_reasoning_extra(cfg: ThinkingConfig) -> dict[str, Any]:
    """
    返回 OpenAI o 系列 the extra_body 字段。
    注意：o 系列不支持 enable_thinking / return_reasoning，
    这些不应透传给 OpenAI。
    """
    if not cfg.enable or cfg.reasoning_effort is None:
        return {}
    effort_map = {"low": "low", "medium": "medium", "high": "high", "max": "high"}
    return {"reasoning_effort": effort_map.get(cfg.reasoning_effort, "medium")}
