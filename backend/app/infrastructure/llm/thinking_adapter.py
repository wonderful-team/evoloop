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


# --- 推理模型判定 ---

#: 已知会返回原生 reasoning_content 的推理模型命名标记。
#: DeepSeek 网关通道（含 deepseek-v4-flash 等非 "r1/reasoner" 命名的推理变体）
#: 也会返回 reasoning_content，需一并纳入。
_REASONING_MODEL_MARKERS = (
    "deepseek",
    "r1",
    "reasoner",
    "reasoning",
    "thinking",
    "think",
    "qwq",
)


def is_reasoning_model(model_name: str, base_url: str = "") -> bool:
    """保守判定模型是否为推理模型（会返回原生 reasoning_content）。

    用于是否启用 content→reasoning 迁移：避免普通 Chat 模型的开场白
    （如 "Let me search for that..."）被误存为 reasoning_content，
    回传给下一轮请求时被 Provider 拒绝。

    Args:
        model_name: 模型名。
        base_url: 可选的 base_url，用于识别 Anthropic/OpenAI 等家族。
    """
    n = (model_name or "").lower()
    if detect_model_family(n, base_url) == "openai_reasoning":
        return True
    return any(m in n for m in _REASONING_MODEL_MARKERS)


# --- 推理内容提取 ---


def extract_reasoning_from_kwargs(additional_kwargs: dict | None) -> str | None:
    """从 additional_kwargs 提取推理内容（优先 unified "thinking"，回退 reasoning_content）。"""
    if not additional_kwargs:
        return None

    # 1. Prefer unified "thinking" key
    thinking = additional_kwargs.get("thinking")
    if isinstance(thinking, str):
        return thinking if thinking.strip() else None

    # 2. Fallback to raw reasoning_content
    reasoning = additional_kwargs.get("reasoning_content")
    if reasoning:
        res = str(reasoning)
        return res if res.strip() else None
    return None


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
