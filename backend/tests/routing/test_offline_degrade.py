"""Offline / dependency-down degradation for voice routing (design §14.7 offline).

When the embedding provider (LM Studio) is down or unconfigured, retrieval must
return zero candidates and the router must degrade to `agent` delegate — never
raise through the voice WebSocket handler (§8.5).
"""

from __future__ import annotations

import pytest

from app.core.routing import retriever, router
from app.core.routing.schemas import RouteRequest


class _BoomEmbedder:
    async def embed_query(self, _text):
        raise ConnectionError("LM Studio unreachable")  # OSError subclass -> degraded


@pytest.mark.unit
@pytest.mark.asyncio
async def test_embed_down_returns_zero_candidates(monkeypatch) -> None:
    monkeypatch.setattr(retriever, "_get_embedder", lambda: _BoomEmbedder())

    candidates = await retriever.retrieve("打开微信")

    assert candidates == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_embedder_returns_zero_candidates(monkeypatch) -> None:
    # Fresh install / no DB config: _get_embedder may return None.
    monkeypatch.setattr(retriever, "_get_embedder", lambda: None)

    candidates = await retriever.retrieve("打开微信")

    assert candidates == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_embed_down_degrades_to_delegate_without_llm(monkeypatch) -> None:
    """End-to-end: embed failure -> [] -> router delegates, LLM never called."""
    monkeypatch.setattr(retriever, "_get_embedder", lambda: _BoomEmbedder())
    monkeypatch.setattr(router, "_min_score", lambda: 0.55)

    async def _boom():
        raise AssertionError("LLM must not be called when there are no candidates")

    monkeypatch.setattr(router, "_create_route_llm", _boom)

    candidates = await retriever.retrieve("打开微信")
    decision = await router.route(RouteRequest(text="打开微信", thread_id="t"), candidates)

    assert candidates == []
    assert decision.target_type == "agent"  # clean degrade, no exception
