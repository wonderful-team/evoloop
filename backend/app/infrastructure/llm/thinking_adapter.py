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
    返回: "anthropic" | "openai_reasoning" | "kimi" | "zhipu" | "minimax" | "gemini" | "openai_compat"
    """
    n = model_name.lower()
    u = (base_url or "").lower()
    if "claude" in n or "anthropic" in u:
        return "anthropic"
    if any(n.startswith(p) for p in ("o1", "o3", "o4")):
        return "openai_reasoning"
    if "kimi" in n or "moonshot" in u:
        return "kimi"
    if "glm" in n or "zhipu" in u or "bigmodel" in u:
        return "zhipu"
    if "minimax" in n or "minimax" in u:
        return "minimax"
    if "gemini" in n or "google" in u:
        return "gemini"
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
    这两个 Kimi 专用字段不应透传给 OpenAI。
    """
    if not cfg.enable or cfg.reasoning_effort is None:
        return {}
    effort_map = {"low": "low", "medium": "medium", "high": "high", "max": "high"}
    return {"reasoning_effort": effort_map.get(cfg.reasoning_effort, "medium")}


# --- Kimi / Moonshot ---

_KIMI_EFFORT_TOKENS = {
    "low":    8_000,
    "medium": 16_000,
    "high":   32_000,
    "max":    64_000,
}

def get_kimi_min_max_tokens(cfg: ThinkingConfig) -> int:
    """
    Kimi 没有 budget 参数控制，唯一手段是设置足够大的 max_tokens。
    官方建议 ≥ 16000。按 effort 分档，确保推理+正文都能完整输出。
    """
    return _KIMI_EFFORT_TOKENS.get(cfg.reasoning_effort or "high", 16_000)


# --- Zhipu (GLM-5) ---


def build_zhipu_thinking_extra(cfg: ThinkingConfig) -> dict[str, Any]:
    """
    返回智谱 (GLM-5 等) 开启深度思考的 extra_body 参数格式。
    格式为: {"thinking": {"type": "enabled"}} 或 {"thinking": {"type": "disabled"}}
    """
    if cfg.enable:
        return {"thinking": {"type": "enabled"}}
    return {"thinking": {"type": "disabled"}}


# --- MiniMax (3.x 等) ---


def build_minimax_thinking_extra(cfg: ThinkingConfig) -> dict[str, Any]:
    """
    返回 MiniMax 开启深度思考的 extra_body 参数格式。
    格式为: {"reasoning_split": True} 或 {"reasoning_split": False}
    """
    if cfg.enable:
        return {"reasoning_split": True}
    return {"reasoning_split": False}


# --- Gemini (3.x 等) ---


def build_gemini_thinking_extra(cfg: ThinkingConfig) -> dict[str, Any]:
    """
    返回 Gemini 开启深度思考的 extra_body 参数格式。
    注意：在 OpenAI 兼容网关中，有些网关支持直接透传 generation_config，
    有些网关支持 thinking_config 字段。我们同时写入这两种形式以达到最大兼容。
    """
    level_map = {
        "low": "low",
        "medium": "medium",
        "high": "high",
        "max": "high"
    }
    level = level_map.get(cfg.reasoning_effort or "high", "high")
    
    if cfg.enable:
        return {
            "thinking_config": {
                "thinking_level": level
            },
            "generation_config": {
                "thinking_config": {
                    "thinking_level": level
                }
            }
        }
    return {
        "thinking_config": {
            "thinking_level": "minimal"
        }
    }
