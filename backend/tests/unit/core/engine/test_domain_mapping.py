"""Tests for the engine domain -> intent/modules mapping."""

from __future__ import annotations

import pytest

from app.core.engine.domain_mapping import resolve_domain


@pytest.mark.parametrize(
    ("domain", "expected_intent", "expected_modules"),
    [
        ("coding_dev", "worker_task", ["Base", "Skill", "Project"]),
        ("coding_test", "worker_task", ["Base", "Skill", "Project"]),
        ("coding_ops", "worker_task", ["Base", "Skill", "Project"]),
        ("business", "worker_task", ["Base", "Skill", "Project"]),
        ("ecommerce", "worker_task", ["Base", "Skill", "Project"]),
        ("shopping", "worker_task", ["Base", "Skill", "Project"]),
        ("news", "worker_task", ["Base", "Skill", "Project"]),
        ("weather", "worker_task", ["Base", "Skill", "Project"]),
        ("system_info", "environment_query", ["Base", "Environment"]),
        ("memory", "memory_query", ["Base", "Memory"]),
        ("greeting", "direct_answer", ["Base"]),
        ("chitchat", "direct_answer", ["Base"]),
        ("multi_intent", "worker_task", ["Base", "Skill", "Project"]),
        ("media_control", "macro_task", ["Base", "Macro"]),
        ("app_control", "macro_task", ["Base", "Macro"]),
        ("device_control", "macro_task", ["Base", "Macro"]),
        ("session_control", "builtin_task", ["Base"]),
        ("ambiguous", "ambiguous", ["Base", "Memory", "Environment"]),
        ("unknown_domain", "ambiguous", ["Base", "Memory", "Environment"]),
        (None, "ambiguous", ["Base", "Memory", "Environment"]),
    ],
)
def test_resolve_domain(
    domain: str | None, expected_intent: str, expected_modules: list[str]
) -> None:
    intent, modules = resolve_domain(domain)
    assert intent == expected_intent
    assert modules == expected_modules
