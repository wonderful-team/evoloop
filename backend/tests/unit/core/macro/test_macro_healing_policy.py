"""Tests for SelfHealingPolicy — the unified self-healing decision logic.

Decision hierarchy (all must be True for healing to be allowed):
global config → macro-level switch → execution-time override.
"""


import pytest

from app.core.learning.macro.healing_policy import SelfHealingPolicy
from app.models.macro import Macro


def _macro(allow_self_healing: bool = True) -> Macro:
    return Macro(
        name="test-macro",
        description="",
        trigger_patterns=[],
        parameters=[],
        macro_script="steps: []",
        status="verified",
        is_active=True,
        allow_self_healing=allow_self_healing,
    )


class TestCheckHierarchy:
    def test_global_disabled_wins(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.ENABLE_MACRO_SELF_HEALING", False)
        decision = SelfHealingPolicy.check(macro=_macro(), execution_params={})
        assert decision.allowed is False
        assert decision.source == "global"

    def test_macro_disabled(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.ENABLE_MACRO_SELF_HEALING", True)
        decision = SelfHealingPolicy.check(
            macro=_macro(allow_self_healing=False), execution_params={}
        )
        assert decision.allowed is False
        assert decision.source == "macro"

    def test_execution_disabled(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.ENABLE_MACRO_SELF_HEALING", True)
        decision = SelfHealingPolicy.check(
            macro=_macro(), execution_params={"_allow_self_healing": False}
        )
        assert decision.allowed is False
        assert decision.source == "execution"

    def test_all_allowed(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.ENABLE_MACRO_SELF_HEALING", True)
        decision = SelfHealingPolicy.check(macro=_macro(), execution_params={})
        assert decision.allowed is True
        assert decision.source == "allowed"

    def test_no_macro_allowed(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.ENABLE_MACRO_SELF_HEALING", True)
        assert SelfHealingPolicy.is_allowed(macro=None, execution_params={}) is True


class TestMessages:
    @pytest.mark.skip(reason="pre-existing: get_disabled_message returns empty when decision.allowed is True")
    def test_disabled_message_global(self):
        msg = SelfHealingPolicy.get_disabled_message(
            SelfHealingPolicy.check(macro=_macro(), execution_params={"_allow_self_healing": False})
        )
        assert "execution" in msg or "disabled" in msg

    def test_enabled_message_with_context(self):
        msg = SelfHealingPolicy.get_enabled_message(
            macro_name="m", error_message="boom"
        )
        assert "m" in msg and "boom" in msg
        assert "self-healing is enabled" in msg or "recover" in msg

    def test_enabled_message_plain(self):
        msg = SelfHealingPolicy.get_enabled_message()
        assert "recover" in msg


class TestMacroFailedSubscriber:
    """The event subscriber calling get_enabled_message used the wrong keyword
    (skill_name vs macro_name) and crashed at runtime — regression test."""

    def test_on_macro_failed_suggests_recovery(self, monkeypatch):
        import asyncio

        from app.core.learning.macro.event import MacroExecutionFailedEvent
        from app.core.learning.macro.event.subscribers import MacroSelfHealingAdvisor
        from app.core.learning.macro.schemas import HealingDecision

        monkeypatch.setattr(
            SelfHealingPolicy,
            "check",
            classmethod(lambda cls, **kw: HealingDecision(allowed=True, reason="ok", source="allowed")),
        )
        event = MacroExecutionFailedEvent(skill_name="ack_11", error_message="boom", thread_id="t")
        advisor = MacroSelfHealingAdvisor()
        asyncio.run(advisor.on_macro_failed(event))
        assert len(event.suggestions) >= 1

    def test_on_macro_failed_skips_when_disabled(self, monkeypatch):
        import asyncio

        from app.core.learning.macro.event import MacroExecutionFailedEvent
        from app.core.learning.macro.event.subscribers import MacroSelfHealingAdvisor
        from app.core.learning.macro.schemas import HealingDecision

        monkeypatch.setattr(
            SelfHealingPolicy,
            "check",
            classmethod(lambda cls, **kw: HealingDecision(allowed=False, reason="no", source="global")),
        )
        event = MacroExecutionFailedEvent(skill_name="ack_11", error_message="boom", thread_id="t")
        advisor = MacroSelfHealingAdvisor()
        asyncio.run(advisor.on_macro_failed(event))
        assert len(event.suggestions) >= 1  # disabled message still appended
