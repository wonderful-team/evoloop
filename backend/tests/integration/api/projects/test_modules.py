"""Integration tests for projects/modules.py routes (mounted at /project-modules)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _mock_check_benefit(monkeypatch):
    monkeypatch.setattr("app.api.deps.check_benefit", AsyncStub(True))


class TestBudgetList:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.modules.evocloud_manager",
            SimpleNamespace(
                api=SimpleNamespace(
                    get_budget_list=AsyncStub({"code": 0, "data": {"items": []}})
                )
            ),
        )
        resp = await client.get(
            "/project-modules/budget/list?project_id=1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200

    async def test_passes_params(self, client, monkeypatch):
        received = {}

        async def _get_budget_list(project_id, page, page_size, token=None):
            received["project_id"] = project_id
            received["page"] = page
            received["page_size"] = page_size
            received["token"] = token
            return {"code": 0, "data": {}}

        monkeypatch.setattr(
            "app.api.routes.projects.modules.evocloud_manager",
            SimpleNamespace(api=SimpleNamespace(get_budget_list=_get_budget_list)),
        )
        resp = await client.get(
            "/project-modules/budget/list?project_id=42&page=2&page_size=10",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert received["project_id"] == 42
        assert received["page"] == 2
        assert received["page_size"] == 10


class TestBudgetOverview:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.modules.evocloud_manager",
            SimpleNamespace(
                api=SimpleNamespace(
                    get_budget_overview=AsyncStub({"code": 0, "data": {"total": 100}})
                )
            ),
        )
        resp = await client.get(
            "/project-modules/budget/overview?project_id=1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200


class TestTimesheetList:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.modules.evocloud_manager",
            SimpleNamespace(
                api=SimpleNamespace(
                    get_timesheet_list=AsyncStub({"code": 0, "data": {"rows": []}})
                )
            ),
        )
        resp = await client.get(
            "/project-modules/timesheet/list?project_id=1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"rows": []}

    async def test_error_from_cloud(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.modules.evocloud_manager",
            SimpleNamespace(
                api=SimpleNamespace(
                    get_timesheet_list=AsyncStub(
                        {"code": -1, "message": "cloud error"}
                    )
                )
            ),
        )
        resp = await client.get(
            "/project-modules/timesheet/list?project_id=1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 400


class TestTimesheetQuickAdd:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.modules.evocloud_manager",
            SimpleNamespace(
                api=SimpleNamespace(
                    add_timesheet_quick=AsyncStub({"code": 0, "message": "ok"})
                )
            ),
        )
        resp = await client.post(
            "/project-modules/timesheet/quick_add",
            json={
                "project_id": 1,
                "hours": 2.5,
                "description": "fixed bug",
                "work_type": "development",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    async def test_error_from_cloud(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.modules.evocloud_manager",
            SimpleNamespace(
                api=SimpleNamespace(
                    add_timesheet_quick=AsyncStub(
                        {"code": -1, "message": "failed"}
                    )
                )
            ),
        )
        resp = await client.post(
            "/project-modules/timesheet/quick_add",
            json={
                "project_id": 1,
                "hours": 1,
                "description": "x",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 400


class TestProjectStatistics:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.modules.evocloud_manager",
            SimpleNamespace(
                api=SimpleNamespace(
                    get_project_statistics=AsyncStub(
                        {"code": 0, "data": {"commits": 42}}
                    )
                )
            ),
        )
        resp = await client.get(
            "/project-modules/statistics/project?project_id=1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"commits": 42}

    async def test_error_from_cloud(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.modules.evocloud_manager",
            SimpleNamespace(
                api=SimpleNamespace(
                    get_project_statistics=AsyncStub(
                        {"code": -1, "message": "fail"}
                    )
                )
            ),
        )
        resp = await client.get(
            "/project-modules/statistics/project?project_id=1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 400


# ---------- helpers ----------


class AsyncStub:
    def __init__(self, return_value):
        self._value = return_value

    async def __call__(self, *args, **kwargs):  # noqa: ARG002
        return self._value
