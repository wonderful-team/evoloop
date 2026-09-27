"""Integration tests for /maintenance memory route
(app/api/routes/memory/maintenance.py).

Covers the single endpoint ``POST /maintenance/deduplicate-checkpoints`` —
success and failure paths.
"""

from __future__ import annotations


class TestDeduplicateCheckpoints:
    async def test_deduplicate_checkpoints(self, client, fake_manager):
        async def _dedupe(*, dry_run=False):
            assert dry_run is False
            return {"removed": 5, "checked": 100}

        fake_manager.deduplicate_checkpoints = _dedupe
        resp = await client.post(
            "/memory/maintenance/deduplicate-checkpoints", params={"dry_run": "false"}
        )
        assert resp.status_code == 200
        assert resp.json()["removed"] == 5

    async def test_deduplicate_checkpoints_dry_run_default(
        self, client, fake_manager
    ):
        async def _dedupe(*, dry_run=True):
            assert dry_run is True
            return {"removed": 0, "dry_run": True}

        fake_manager.deduplicate_checkpoints = _dedupe
        resp = await client.post("/memory/maintenance/deduplicate-checkpoints")
        assert resp.status_code == 200
        assert resp.json()["dry_run"] is True

    async def test_deduplicate_checkpoints_500(self, client, fake_manager):
        async def _boom(**_kwargs):
            raise RuntimeError("maintenance failed")

        fake_manager.deduplicate_checkpoints = _boom
        resp = await client.post("/memory/maintenance/deduplicate-checkpoints")
        assert resp.status_code == 500
