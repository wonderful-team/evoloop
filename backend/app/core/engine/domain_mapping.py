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

DOMAIN_TO_INTENT_MODULES: dict[str, tuple[str, list[str]]] = {
    # Knowledge / task domains that delegate to the worker agent
    "coding_dev": ("worker_task", ["Base", "Skill", "Project"]),
    "coding_test": ("worker_task", ["Base", "Skill", "Project"]),
    "coding_ops": ("worker_task", ["Base", "Skill", "Project"]),
    "business": ("worker_task", ["Base", "Skill", "Project"]),
    "ecommerce": ("worker_task", ["Base", "Skill", "Project"]),
    "shopping": ("worker_task", ["Base", "Skill", "Project"]),
    "legal": ("worker_task", ["Base", "Skill", "Project"]),
    "medical": ("worker_task", ["Base", "Skill", "Project"]),
    "marketing": ("worker_task", ["Base", "Skill", "Project"]),
    "travel": ("worker_task", ["Base", "Skill", "Project"]),
    "food": ("worker_task", ["Base", "Skill", "Project"]),
    "sports": ("worker_task", ["Base", "Skill", "Project"]),
    "entertainment": ("worker_task", ["Base", "Skill", "Project"]),
    "research": ("worker_task", ["Base", "Skill", "Project"]),
    "education": ("worker_task", ["Base", "Skill", "Project"]),
    "industry": ("worker_task", ["Base", "Skill", "Project"]),
    "finance": ("worker_task", ["Base", "Skill", "Project"]),
    "daily_life": ("worker_task", ["Base", "Skill", "Project"]),
    "news": ("worker_task", ["Base", "Skill", "Project"]),
    "weather": ("worker_task", ["Base", "Skill", "Project"]),
    # System / host / runtime queries
    "system_info": ("environment_query", ["Base", "Environment"]),
    # Personal memory / recall
    "memory": ("memory_query", ["Base", "Memory"]),
    # Lightweight conversational turns
    "greeting": ("direct_answer", ["Base"]),
    "chitchat": ("direct_answer", ["Base"]),
    # Compound / multi-intent detected by the routing layer
    "multi_intent": ("worker_task", ["Base", "Skill", "Project"]),
    # Local / device / media / conversation actions that L0 usually handles fast.
    # These are included so L1 can catch L0 misses while still mapping to the
    # same functional intent and module set the fast path would have used.
    "media_control": ("macro_task", ["Base", "Macro"]),
    "app_control": ("macro_task", ["Base", "Macro"]),
    "device_control": ("macro_task", ["Base", "Macro"]),
    "session_control": ("builtin_task", ["Base"]),
    # Fallback when the classifier is uncertain or the domain is unknown
    "ambiguous": ("ambiguous", ["Base", "Memory", "Environment"]),
}

DEFAULT_INTENT_MODULES: tuple[str, list[str]] = (
    "ambiguous",
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
