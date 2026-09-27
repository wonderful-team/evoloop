"""Integration tests for /concepts memory routes
(app/api/routes/memory/concepts.py).

Covers all 7 endpoints: list (3 variants), get, add, delete, update — success
and failure paths — via the shared API harness with the memory manager
dependency overridden to a controllable fake.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.memory.models import MemoryEntry, MemoryType


def _make_entry(mem_id: str = "concept_some_concept", title: str = "SomeConcept", **overrides) -> MemoryEntry:
    defaults = {
        "id": mem_id,
        "type": MemoryType.CONCEPT,
        "title": title,
        "content": "description here",
        "description": "description here",
        "tags": ["concept"],
        "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return MemoryEntry(**defaults)


class TestListConcepts:
    async def test_list_concepts(self, client, fake_manager):
        async def _list_memories(**kwargs):
            assert kwargs["type_filter"] == MemoryType.CONCEPT
            return [_make_entry(), _make_entry("concept_b", "B")]

        async def _counts(*_a, **_kw):
            return {"SomeConcept": 3, "B": 1}

        fake_manager.list_memories = _list_memories
        fake_manager.get_concept_episode_counts_batch = _counts

        resp = await client.get("/memory/concepts", params={"project_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["episode_count"] == 3

    async def test_list_concepts_returns_empty_on_error(self, client, fake_manager):
        async def _boom(**_kw):
            raise RuntimeError("db down")

        fake_manager.list_memories = _boom
        resp = await client.get("/memory/concepts", params={"project_id": 1})
        assert resp.status_code == 200
        assert resp.json() == []


class TestListConceptsForMobile:
    async def test_list_concepts_for_mobile(self, client, fake_manager):
        async def _list_memories(**_kwargs):
            return [_make_entry()]

        fake_manager.list_memories = _list_memories
        resp = await client.get("/memory/mobile/concepts", params={"project_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["id"] == "concept_some_concept"
        assert data[0]["name"] == "SomeConcept"
        assert "related_files" in data[0]


class TestListConceptsWithCounts:
    async def test_list_concepts_with_counts(self, client, fake_manager):
        async def _list_memories(**kwargs):
            assert kwargs["limit"] == 50
            return [_make_entry()]

        async def _counts(*_a, **_kw):
            return {"SomeConcept": 2}

        fake_manager.list_memories = _list_memories
        fake_manager.get_concept_episode_counts_batch = _counts
        resp = await client.get("/memory/concepts/list", params={"project_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["episode_count"] == 2


class TestGetConcept:
    async def test_get_concept(self, client, fake_manager):
        async def _get_memory(memory_id):
            assert memory_id == "concept_some_concept"
            return _make_entry(content="the description")

        async def _episodes(*_a, **_kw):
            return [{}, {}]

        fake_manager.get_memory = _get_memory
        fake_manager.find_episodes_by_concept = _episodes

        resp = await client.get(
            "/memory/concepts/Some Concept", params={"project_id": 1}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "SomeConcept"
        assert data["episode_count"] == 2

    async def test_get_concept_404(self, client, fake_manager):
        fake_manager.get_memory = AsyncStubReturning(None)
        resp = await client.get("/memory/concepts/Missing", params={"project_id": 1})
        assert resp.status_code == 404

    async def test_get_concept_500(self, client, fake_manager):
        async def _boom(_memory_id):
            raise RuntimeError("nope")

        fake_manager.get_memory = _boom
        resp = await client.get("/memory/concepts/X", params={"project_id": 1})
        assert resp.status_code == 500


class AsyncStubReturning:
    def __init__(self, value):
        self._value = value

    async def __call__(self, *args, **kwargs):
        return self._value


class TestAddConcept:
    async def test_add_concept(self, client, fake_manager):
        called = {}

        async def _store_concept(**kwargs):
            called.update(kwargs)
            return None

        fake_manager.store_concept = _store_concept
        resp = await client.post(
            "/memory/concepts",
            params={"project_id": 1},
            json={"name": "MyConcept", "description": "desc"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["name"] == "MyConcept"
        assert called["project_id"] == 1
        assert called["member_id"] == 1

    async def test_add_concept_500(self, client, fake_manager):
        async def _boom(**_kwargs):
            raise RuntimeError("storage fail")

        fake_manager.store_concept = _boom
        resp = await client.post(
            "/memory/concepts", params={"project_id": 1},
            json={"name": "X", "description": "d"},
        )
        assert resp.status_code == 500


class TestDeleteConcept:
    async def test_delete_concept(self, client, fake_manager):
        fake_manager.delete_memory = AsyncStubReturning(True)
        resp = await client.delete("/memory/concepts/MyConcept", params={"_project_id": 1})
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    async def test_delete_concept_404(self, client, fake_manager):
        fake_manager.delete_memory = AsyncStubReturning(False)
        resp = await client.delete("/memory/concepts/MyConcept", params={"_project_id": 1})
        assert resp.status_code == 404


class TestUpdateConcept:
    async def test_update_concept(self, client, fake_manager):
        fake_manager.get_memory = AsyncStubReturning(_make_entry())
        saved = {}

        async def _save(memory):
            saved["content"] = memory.content
            return None

        fake_manager.save_memory = _save
        resp = await client.put(
            "/memory/concepts/MyConcept", params={"_project_id": 1},
            json={"description": "new description"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert saved["content"] == "new description"

    async def test_update_concept_404(self, client, fake_manager):
        fake_manager.get_memory = AsyncStubReturning(None)
        resp = await client.put(
            "/memory/concepts/MyConcept", params={"_project_id": 1},
            json={"description": "x"},
        )
        assert resp.status_code == 404
