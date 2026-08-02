"""Tests for macro runner: preflight, cache, VOICE_POLICY, invalidate."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.core.execution.macro.runner import (
    _MACRO_CACHE,
    _SCRIPT_CACHE,
    VOICE_POLICY,
    MacroGateError,
    _collect_sources,
    _get_cached_script,
    _scan_steps_risk,
    invalidate_macro_cache,
    preflight,
)


def _make_macro(
    id=1,
    name="test",
    status="verified",
    is_active=True,
    macro_script="- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: beep\n",
    updated_at=None,
    parameters=None,
):
    macro = MagicMock()
    macro.id = id
    macro.name = name
    macro.status = status
    macro.is_active = is_active
    macro.macro_script = macro_script
    macro.updated_at = updated_at or datetime.now(timezone.utc)
    macro.parameters = parameters or []
    macro.is_routable.return_value = is_active and status == "verified"
    return macro


class TestPreflight:
    def test_preflight_pass(self):
        macro = _make_macro()
        script = preflight(macro, {})
        assert script is not None
        assert len(script.steps) == 1

    def test_preflight_not_routable(self):
        macro = _make_macro(status="pending_review", is_active=False)
        macro.is_routable.return_value = False
        with pytest.raises(MacroGateError, match="not active"):
            preflight(macro, {})

    def test_preflight_missing_params(self):
        macro = _make_macro(parameters=[{"name": "x", "type": "str", "required": True}])
        with pytest.raises(MacroGateError, match="Missing required"):
            preflight(macro, {})

    def test_preflight_with_params(self):
        macro = _make_macro(parameters=[{"name": "x", "type": "str", "required": True}])
        script = preflight(macro, {"x": "hello"})
        assert script is not None

    def test_preflight_bad_yaml(self):
        macro = _make_macro(macro_script="bad: yaml:\n  - [broken\n")
        with pytest.raises(MacroGateError, match="Failed to parse"):
            preflight(macro, {})


class TestCache:
    def setup_method(self):
        _SCRIPT_CACHE.clear()
        _MACRO_CACHE.clear()

    def test_get_cached_script_first_call(self):
        macro = _make_macro()
        script = _get_cached_script(macro)
        assert script is not None
        assert len(_SCRIPT_CACHE) == 1

    def test_get_cached_script_second_call(self):
        macro = _make_macro()
        s1 = _get_cached_script(macro)
        s2 = _get_cached_script(macro)
        assert s1 is s2

    def test_get_cached_script_invalidated_on_update(self):
        macro = _make_macro(updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
        s1 = _get_cached_script(macro)
        macro.updated_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        s2 = _get_cached_script(macro)
        assert s1 is not s2

    def test_cache_clear_on_500(self):
        for i in range(510):
            m = _make_macro(id=i + 100)
            _get_cached_script(m)
        assert len(_SCRIPT_CACHE) < 100


class TestInvalidateCache:
    def setup_method(self):
        _SCRIPT_CACHE.clear()
        _MACRO_CACHE.clear()

    def test_invalidate_specific(self):
        _SCRIPT_CACHE[1] = ("v1", MagicMock())
        _MACRO_CACHE[1] = ("v1", MagicMock())
        _SCRIPT_CACHE[2] = ("v1", MagicMock())
        invalidate_macro_cache(1)
        assert 1 not in _SCRIPT_CACHE
        assert 1 not in _MACRO_CACHE
        assert 2 in _SCRIPT_CACHE

    def test_invalidate_all(self):
        _SCRIPT_CACHE[1] = ("v1", MagicMock())
        _MACRO_CACHE[1] = ("v1", MagicMock())
        invalidate_macro_cache()
        assert len(_SCRIPT_CACHE) == 0
        assert len(_MACRO_CACHE) == 0


class TestVOICEPOLICY:
    def test_voice_policy_no_family_restriction(self):
        steps = [MagicMock(type="action", event_type="applescript", source="desktop")]
        reason = _scan_steps_risk(steps, VOICE_POLICY)
        assert reason is None

    def test_voice_policy_no_risk_restriction(self):
        steps = [MagicMock(type="action", event_type="native", source="desktop")]
        reason = _scan_steps_risk(steps, VOICE_POLICY)
        assert reason is None

    def test_voice_policy_self_heal_disabled(self):
        assert VOICE_POLICY.allow_self_heal is False

    def test_voice_policy_allowed_sources(self):
        assert "desktop" in VOICE_POLICY.allowed_sources
        assert "dom" not in VOICE_POLICY.allowed_sources
        assert "mobile" not in VOICE_POLICY.allowed_sources

    def test_voice_policy_rejects_global_source(self):
        assert "global" not in VOICE_POLICY.allowed_sources


class TestCollectSources:
    def test_collects_desktop_source(self):
        steps = [MagicMock(type="action", source="desktop")]
        sources = _collect_sources(steps)
        assert "desktop" in sources

    def test_collects_nested_sources(self):
        inner = MagicMock(type="action", source="dom")
        outer = MagicMock(type="action", source="desktop", then_steps=[inner])
        sources = _collect_sources([outer])
        assert "desktop" in sources
        assert "dom" in sources
