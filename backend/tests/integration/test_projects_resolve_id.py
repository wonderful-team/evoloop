"""Verification of _resolve_project_id consolidation (projects/_listing.py)."""

from __future__ import annotations

from app.api.routes.projects.listing import _resolve_project_id


class TestResolveProjectId:
    def test_uses_project_id_when_present(self) -> None:
        assert _resolve_project_id({"project_id": 42, "id": 99}) == 42

    def test_falls_back_to_id(self) -> None:
        assert _resolve_project_id({"id": 7}) == 7

    def test_string_values_coerced_to_int(self) -> None:
        assert _resolve_project_id({"project_id": "123"}) == 123

    def test_missing_keys_returns_none(self) -> None:
        assert _resolve_project_id({}) is None
        assert _resolve_project_id({"name": "proj"}) is None

    def test_none_project_id_falls_back(self) -> None:
        assert _resolve_project_id({"project_id": None, "id": 5}) == 5
