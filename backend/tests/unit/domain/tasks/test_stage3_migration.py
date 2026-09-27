"""Stage 3 migration tests — template integrity, dedup idempotency, domains."""

from __future__ import annotations

from scripts.migrate_business_poll import CHECKLISTS


def test_templates_complete():
    """All six legacy prompts have a full executable instruction template."""
    expected = {
        "poll-orders-pending",
        "poll-refunds-pending",
        "poll-low-stock",
        "poll-member-abnormal",
        "poll-promotion-expiring",
        "poll-finance-abnormal",
    }
    assert set(CHECKLISTS) == expected
    for meta in CHECKLISTS.values():
        assert meta["title"]
        assert meta["category"]
        # the prompt IS the task body the agent executes
        assert len(meta["prompt"]) >= 60
        assert "无待办" in meta["prompt"] or "无待办」" in meta["prompt"]


def test_capital_patrols_never_execute():
    """Capital-related patrols only propose (T1/T2), never execute."""
    for pid in ("poll-finance-abnormal", "poll-member-abnormal"):
        prompt = CHECKLISTS[pid]["prompt"]
        assert "建提案" in prompt
        assert ("禁止" in prompt) or ("仅汇报" in prompt)
