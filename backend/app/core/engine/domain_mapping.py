"""Domain -> functional intent/modules mapping.

The routing layer (L1) classifies an utterance into a domain label and stores it
in ``IntentHint.domain``.  The agent engine uses this module to map that domain
into a concrete functional ``intent`` and the set of context modules that should
be loaded for the turn.

This keeps the L1 classifier focused on pure domain classification; product
changes (e.g. adding a Health module for medical questions) only require an edit
here, not a model retrain.
"""

from __future__ import annotations

from app.core.routing.constants import (
    DOMAIN_AMBIGUOUS,
    INTENT_DIRECT_ANSWER,
    INTENT_ENVIRONMENT_QUERY,
    INTENT_MACRO_TASK,
    INTENT_MEMORY_QUERY,
    INTENT_WORKER_TASK,
)

DOMAIN_TO_INTENT_MODULES: dict[str, tuple[str, list[str]]] = {
    # 注：宿主/项目声明域（如 mall_ops）的 modules 由 capability profile 提供
    # （AgentContextHydrator profile-first），不在此注册——引擎保持通用。
    # Knowledge / task domains that delegate to the worker agent
    "coding_dev": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "coding_test": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "coding_ops": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "business": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "ecommerce": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "shopping": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "legal": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "medical": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "marketing": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "travel": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "food": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "sports": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "entertainment": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "research": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "education": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "industry": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "finance": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "daily_life": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "news": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    "weather": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    # System / host / runtime queries
    "system_info": (INTENT_ENVIRONMENT_QUERY, ["Base", "Environment"]),
    # Personal memory / recall
    "memory": (INTENT_MEMORY_QUERY, ["Base", "Memory"]),
    # Lightweight conversational turns
    "greeting": (INTENT_DIRECT_ANSWER, ["Base"]),
    "chitchat": (INTENT_DIRECT_ANSWER, ["Base"]),
    # Session-level control ("再见/拜拜/退出对话") — resolved by the L1 agent
    # as a light direct answer; keep it out of the ambiguous full-context bucket.
    "session_control": (INTENT_DIRECT_ANSWER, ["Base"]),
    # Compound / multi-intent detected by the routing layer
    "multi_intent": (INTENT_WORKER_TASK, ["Base", "Skill", "Project"]),
    # Local / device / media / conversation actions that L0 usually handles fast.
    # These are included so L1 can catch L0 misses while still mapping to the
    # same functional intent and module set the fast path would have used.
    "media_control": (INTENT_MACRO_TASK, ["Base", "Macro"]),
    "app_control": (INTENT_MACRO_TASK, ["Base", "Macro"]),
    "device_control": (INTENT_MACRO_TASK, ["Base", "Macro"]),
    # Fallback when the classifier is uncertain or the domain is unknown
    "ambiguous": (DOMAIN_AMBIGUOUS, ["Base", "Memory", "Environment"]),
}

DEFAULT_INTENT_MODULES: tuple[str, list[str]] = (
    DOMAIN_AMBIGUOUS,
    ["Base", "Memory", "Environment"],
)


def resolve_domain(domain: str | None) -> tuple[str, list[str]]:
    """Return the functional intent and module list for a domain label."""
    if not domain:
        return DEFAULT_INTENT_MODULES
    return DOMAIN_TO_INTENT_MODULES.get(domain, DEFAULT_INTENT_MODULES)


__all__ = [
    "DOMAIN_TO_INTENT_MODULES",
    "DEFAULT_INTENT_MODULES",
    "resolve_domain",
]
