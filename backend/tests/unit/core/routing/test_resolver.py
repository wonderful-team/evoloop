"""Unit tests for the cross-intent param resolver (方案甲)."""

from __future__ import annotations

import pytest

from app.core.routing.resolver import (
    ResolveError,
    resolve_expression,
    resolve_params,
)


class TestResolveExpression:
    def test_simple_ratio(self):
        prior = {1: {"price": 100.0}}
        assert resolve_expression("{{1.price}} * 0.9", prior) == 90.0

    def test_currency_text_coerced(self):
        prior = {1: {"value": "￥99.50"}}
        assert resolve_expression("round({{1.value}} - 5, 2)", prior) == 94.5

    def test_absolute_decrement(self):
        prior = {1: {"stock": 50}}
        assert resolve_expression("{{1.stock}} - 3", prior) == 47.0

    def test_multiple_refs(self):
        prior = {1: {"price": 100.0}, 2: {"rate": 0.8}}
        assert resolve_expression("{{1.price}} * {{2.rate}}", prior) == 80.0

    def test_nested_key(self):
        prior = {1: {"rows": {"price": 42}}}
        assert resolve_expression("{{1.rows.price}} + 8", prior) == 50.0

    def test_funcs(self):
        prior = {1: {"p": 3.7}}
        assert resolve_expression("max({{1.p}}, 5)", prior) == 5.0
        assert resolve_expression("abs(0 - {{1.p}})", prior) == 3.7

    def test_missing_intent_rejected(self):
        with pytest.raises(ResolveError, match="没有产出数据"):
            resolve_expression("{{2.price}} * 0.9", {1: {"price": 1}})

    def test_missing_key_rejected(self):
        with pytest.raises(ResolveError, match="没有 'stock'"):
            resolve_expression("{{1.stock}} + 1", {1: {"price": 1}})

    def test_non_numeric_rejected(self):
        with pytest.raises(ResolveError, match="不是数值"):
            resolve_expression("{{1.name}} * 2", {1: {"name": "铰链"}})

    def test_division_by_zero_rejected(self):
        with pytest.raises(ResolveError, match="除数为零"):
            resolve_expression("{{1.a}} / 0", {1: {"a": 1}})

    def test_code_injection_rejected(self):
        with pytest.raises(ResolveError):
            resolve_expression("__import__('os').system('id')", {})
        with pytest.raises(ResolveError):
            resolve_expression("open('/etc/passwd').read()", {})
        with pytest.raises(ResolveError):
            resolve_expression("[x for x in range(10)]", {})

    def test_string_constant_rejected(self):
        with pytest.raises(ResolveError):
            resolve_expression("'abc'", {})


class TestResolveParams:
    def test_batch(self):
        prior = {1: {"price": 200.0}}
        out = resolve_params(
            {"new_value": "{{1.price}} * 0.9", "qty": "{{1.price}} / 100"}, prior
        )
        assert out == {"new_value": 180.0, "qty": 2.0}
