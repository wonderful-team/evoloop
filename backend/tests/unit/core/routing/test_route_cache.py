"""Unit tests for the route-decision cache (report §四十)."""

from __future__ import annotations

import pytest

from app.core.routing import route_cache
from app.core.routing.schemas import RouteDecision


@pytest.fixture(autouse=True)
def _clean_cache():
    route_cache.clear()
    yield
    route_cache.clear()


def _decision(macro_id: int = 107) -> RouteDecision:
    return RouteDecision(
        status="routed",
        target_type="macro",
        target={"id": macro_id},
        params={"query": "夜光亚克力钥匙扣"},
        raw=None,
    )


def test_enabled_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ROUTE_CACHE_ENABLED", raising=False)
    assert route_cache.enabled() is True
    monkeypatch.setenv("ROUTE_CACHE_ENABLED", "0")
    assert route_cache.enabled() is False
    monkeypatch.setenv("ROUTE_CACHE_ENABLED", "off")
    assert route_cache.enabled() is False


def test_normalize_strips_punct_and_case() -> None:
    assert route_cache.normalize(" 查库存。 ") == route_cache.normalize("查库存")
    assert route_cache.normalize("查库存？") == route_cache.normalize("查库存")
    assert route_cache.normalize("Open App") == route_cache.normalize("open app")
    assert route_cache.normalize("查库存") != route_cache.normalize("查价格")


def test_put_get_roundtrip() -> None:
    route_cache.put("v1|查库存", [_decision()])
    got = route_cache.get("v1|查库存")
    assert got is not None
    assert got[0].target["id"] == 107
    assert got[0].params["query"] == "夜光亚克力钥匙扣"
    assert route_cache.stats()["hits"] == 1


def test_version_change_invalidates() -> None:
    route_cache.put("v1|查库存", [_decision()])
    assert route_cache.get("v2|查库存") is None  # index rebuilt -> miss
    assert route_cache.get("v1|查库存") is not None


def test_ttl_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(route_cache.time, "monotonic", lambda: now[0])
    route_cache.put("v1|a", [_decision()])
    assert route_cache.get("v1|a") is not None
    now[0] += route_cache._TTL_SEC + 1
    assert route_cache.get("v1|a") is None


def test_lru_eviction() -> None:
    for i in range(route_cache._MAX_ENTRIES + 10):
        route_cache.put(f"v1|t{i}", [_decision()])
    assert route_cache.stats()["entries"] == route_cache._MAX_ENTRIES
    assert route_cache.get("v1|t0") is None  # oldest evicted
    assert route_cache.get(f"v1|t{route_cache._MAX_ENTRIES + 9}") is not None


def test_put_none_key_is_noop() -> None:
    route_cache.put(None, [_decision()])
    assert route_cache.stats()["entries"] == 0


