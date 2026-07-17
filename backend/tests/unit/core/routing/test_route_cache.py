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


# ── route_many integration ────────────────────────────────────


@pytest.mark.asyncio
async def test_route_many_caches_second_call(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.routing import router
    from app.core.routing.schemas import RouteRequest

    monkeypatch.setenv("ROUTE_CACHE_ENABLED", "1")
    monkeypatch.setattr(route_cache, "key_for", _async_return("vTEST"))

    calls = {"route": 0}

    async def fake_route(_req, _candidates):
        calls["route"] += 1
        return _decision()

    async def fake_decompose(_text):
        return []  # single intent

    monkeypatch.setattr(router, "route", fake_route)
    monkeypatch.setattr("app.core.routing.decompose.decompose", fake_decompose)

    req = RouteRequest(text="查一下夜光亚克力钥匙扣的库存", thread_id="t1")
    first = await router.route_many(req, [])
    second = await router.route_many(req, [])
    assert calls["route"] == 1, "第二次应命中缓存，不再调 route()"
    assert first[0].target == second[0].target


@pytest.mark.asyncio
async def test_route_many_cache_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.routing import router
    from app.core.routing.schemas import RouteRequest

    monkeypatch.setenv("ROUTE_CACHE_ENABLED", "0")
    calls = {"route": 0}

    async def fake_route(_req, _candidates):
        calls["route"] += 1
        return _decision()

    async def fake_decompose(_text):
        return []

    monkeypatch.setattr(router, "route", fake_route)
    monkeypatch.setattr("app.core.routing.decompose.decompose", fake_decompose)

    req = RouteRequest(text="查库存", thread_id="t1")
    await router.route_many(req, [])
    await router.route_many(req, [])
    assert calls["route"] == 2, "禁用缓存时每次都走 route()"


@pytest.mark.asyncio
async def test_clarify_never_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.routing import router, session_frame
    from app.core.routing.schemas import RouteRequest

    monkeypatch.setenv("ROUTE_CACHE_ENABLED", "1")
    monkeypatch.setattr(route_cache, "key_for", _async_return("vTEST"))
    session_frame.clear_frame("t-clarify")

    req = RouteRequest(text="把它的库存改成142", thread_id="t-clarify")
    d1 = await router.route_many(req, [])
    assert d1[0].status == "clarify"
    assert route_cache.stats()["entries"] == 0, "clarify 决策不得入缓存"
    session_frame.clear_frame("t-clarify")


def _async_return(value):
    async def _f(*_a, **_kw):
        return value

    return _f
