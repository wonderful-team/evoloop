"""Integration tests for /episodes memory route
(app/api/routes/memory/episodes.py).

Covers the single endpoint ``GET /episodes/by-concept`` — success and failure
paths.
"""

from __future__ import annotations


class TestGetEpisodesByConcept:
    async def test_get_episodes_by_concept(self, client, fake_manager):
        async def _find(*_a, **_kw):
            return [
                {"id": "e1", "goal": "g1", "result": "r1", "timestamp": "t1"},
                {"id": "e2", "goal": "g2", "result": "r2", "timestamp": "t2"},
            ]

        fake_manager.find_episodes_by_concept = _find
        resp = await client.get(
            "/memory/episodes/by-concept",
            params={"project_id": 1, "concept": "MyConcept", "limit": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == "e1"
        assert data[0]["error"] is None

    async def test_get_episodes_by_concept_empty_concept(self, client, fake_manager):
        resp = await client.get(
            "/memory/episodes/by-concept", params={"project_id": 1, "concept": ""}
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_episodes_by_concept_error_returns_empty(
        self, client, fake_manager
    ):
        async def _boom(*_a, **_kw):
            raise RuntimeError("neo4j down")

        fake_manager.find_episodes_by_concept = _boom
        resp = await client.get(
            "/memory/episodes/by-concept",
            params={"project_id": 1, "concept": "MyConcept"},
        )
        assert resp.status_code == 200
        assert resp.json() == []
