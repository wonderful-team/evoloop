"""App-level constants for the core.engine package.

Consolidates module-level constants that were previously spread across
engine submodules, so numeric/list/tuple tuning values are not buried in
business logic.

Engine enums (MessageCategory, EventType, RewindEventType, ...) live
in their own dedicated enum modules (message/category.py,
event/types.py, rewind/event/types.py) and are intentionally NOT moved here.
Cross-subsystem (global) contract constants belong in ``app.constants``.
"""

import openai

# ====================== Goal distillation ======================
#: 会话目标归一化后最大长度（字符）
GOAL_MAX_LENGTH = 500
#: 会话目标用于展示的最大长度（字符）
GOAL_DISPLAY_MAX_LENGTH = 200

# ====================== Engine command actions ======================
#: 引擎支持的远程命令动作集合
ENGINE_ACTIONS: set[str] = {
    "chat",
    "stop",
    "retry",
    "rewind",
    "hitl_response",
    "hitl_cancel",
    "memory_add",
    "memory_update",
    "memory_delete",
    "a2a_task",
    "a2a_callback",
}

# ====================== LLM error handling ======================
#: 视为可重试/兜底处理的 LLM 异常集合
LLM_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ValueError,
    OSError,
    RuntimeError,
    TypeError,
    KeyError,
    AttributeError,
    openai.APIError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.AuthenticationError,
    openai.BadRequestError,
    openai.ConflictError,
    openai.InternalServerError,
    openai.NotFoundError,
    openai.PermissionDeniedError,
    openai.RateLimitError,
    openai.UnprocessableEntityError,
)

# ====================== Token filtering ======================
#: 应隐藏的审计标签起始标记
HIDDEN_TAGS_START: list[str] = [
    "<evoloop_session_audit>",
    "<evoloop_audit_outcome>",
    "<evoloop_audit_reason>",
    "<evoloop_audit_proof>",
]
#: 应隐藏的审计标签结束标记
HIDDEN_TAGS_END: list[str] = [
    "</evoloop_session_audit>",
    "</evoloop_audit_outcome>",
    "</evoloop_audit_reason>",
    "</evoloop_audit_proof>",
]
#: 应从输出剥离的标签
STRIP_TAGS: list[str] = [
    "<evoloop_final_report>",
    "</evoloop_final_report>",
    "</s>",
    "<|im_end|>",
    "<|endoftext|>",
]

# ====================== Artifact extraction ======================
#: 代码块语言标识 → 落地文件类型的映射
ARTIFACT_CODE_BLOCK_TYPES: dict[str, str] = {
    "mermaid": "mermaid",
    "map": "map",
    "artifact": "html",
    "html": "html",
    "react": "react",
}
