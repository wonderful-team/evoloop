"""Unit tests for atlas API route helpers (generate_app_map guards)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import app.api.routes.atlas as atlas_routes


@pytest.mark.asyncio
async def test_generate_app_map_missing_project_404():
    with patch.object(
        atlas_routes, "get_project_path", new=AsyncMock(return_value=None)
    ):
        req = SimpleNamespace(project_id=999, entity="goods", force_regenerate=False)
        with pytest.raises(HTTPException) as exc:
            await atlas_routes.generate_app_map(
                req, bg_tasks=None, _token=None, current_user=None
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_generate_app_map_requires_entity():
    req = SimpleNamespace(project_id=1, entity="", force_regenerate=False)
    with (
        patch.object(
            atlas_routes, "get_project_path", new=AsyncMock(return_value="/tmp/proj")
        ),
        patch("os.path.isdir", return_value=True),
    ):
        with pytest.raises(HTTPException) as exc:
            await atlas_routes.generate_app_map(
                req, bg_tasks=None, _token=None, current_user=None
            )
    assert exc.value.status_code == 400
