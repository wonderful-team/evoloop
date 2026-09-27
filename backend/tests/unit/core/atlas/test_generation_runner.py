"""Unit tests for the generation runner's AppMap batch write (macro-free)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.domain.codebase.generation.runner import batch_write_appmaps


@pytest.mark.asyncio
async def test_batch_write_appmaps_counts_written_and_skipped():
    entities = {
        "goods": {"platform": "web", "aliases": ["商品"], "routes": [], "actions": [], "elements": [], "db_tables": [], "extra": {}},
        "order": {"platform": "web", "aliases": ["订单"], "routes": [], "actions": [], "elements": [], "db_tables": [], "extra": {}},
    }

    async def fake_save_app_map(**kwargs):
        # first call creates, second call is unchanged
        if kwargs["entity"] == "goods":
            return (1, 1, True)
        return (1, 1, False)

    with patch(
        "app.core.atlas.source.persistence.save_app_map",
        new=AsyncMock(side_effect=fake_save_app_map),
    ):
        result = await batch_write_appmaps(project_id=1, entities=entities)

    assert result["written"] == 1
    assert result["skipped"] == 1
    assert result["failed"] == 0
    assert "macros_generated" not in result


@pytest.mark.asyncio
async def test_batch_write_appmaps_counts_failures():
    entities = {
        "goods": {"platform": "web", "aliases": [], "routes": [], "actions": [], "elements": [], "db_tables": [], "extra": {}},
    }

    async def fake_save_app_map(**kwargs):
        raise RuntimeError("boom")

    with patch(
        "app.core.atlas.source.persistence.save_app_map",
        new=AsyncMock(side_effect=fake_save_app_map),
    ):
        result = await batch_write_appmaps(project_id=1, entities=entities)

    assert result["failed"] == 1
    assert result["written"] == 0
