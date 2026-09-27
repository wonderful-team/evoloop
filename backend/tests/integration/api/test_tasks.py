"""Integration tests for the /evocloud/tasks API routes (app/api/routes/tasks.py)."""

from __future__ import annotations

from types import SimpleNamespace


async def _fake_get_project_tasks(project_id=1, page=1, page_size=50, status=None):  # noqa: ARG001
    return {"code": 0, "data": {"tasks": [{"id": 1, "title": "T1"}], "total": 1}}


async def _fake_get_project_tasks_fail(project_id=1, page=1, page_size=50, status=None):  # noqa: ARG001
    return {"code": -1, "message": "query failed"}


async def _fake_get_task_detail(task_id, token=None):  # noqa: ARG001
    return {
        "code": 0,
        "data": {
            "task_id": task_id,
            "task_title": "Task One",
            "task_desc": "desc",
            "project_id": 1,
            "key_modules_list": [],
            "technical_challenges_list": [],
            "deliverables_list": [],
            "implementation_complexity": "low",
        },
    }


async def _fake_get_task_detail_fail(task_id, token=None):  # noqa: ARG001
    return {"code": -1, "message": "not found"}


async def _fake_get_task_detail_empty(task_id, token=None):  # noqa: ARG001
    return {"code": 0, "data": None}


async def _fake_create_task(data):  # noqa: ARG001
    return {"code": 0, "data": {"task_id": 100}}


async def _fake_create_task_fail(data):  # noqa: ARG001
    return {"code": -1, "message": "create failed"}


async def _fake_update_task(task_id, data):  # noqa: ARG001
    return {"code": 0, "data": {"task_id": task_id}}


async def _fake_update_task_fail(task_id, data):  # noqa: ARG001
    return {"code": -1, "message": "update failed"}


async def _fake_delete_task(task_id):  # noqa: ARG001
    return {"code": 0, "data": {"deleted": True}}


async def _fake_delete_task_fail(task_id):  # noqa: ARG001
    return {"code": -1, "message": "delete failed"}


async def _fake_update_task_status(task_id, status, progress=0):  # noqa: ARG001
    return {"code": 0, "data": {"task_id": task_id, "status": status}}


async def _fake_update_task_status_fail(task_id, status, progress=0):  # noqa: ARG001
    return {"code": -1, "message": "status update failed"}


async def _fake_dispatch(thread_id, message_content, project_id=1, metadata=None):  # noqa: ARG001
    return SimpleNamespace(
        status="ok",
        inputs={"thread_id": thread_id, "message": message_content},
        error=None,
    )


async def _fake_dispatch_fail(thread_id, message_content, project_id=1, metadata=None):  # noqa: ARG001
    return SimpleNamespace(
        status="failed",
        inputs=None,
        error="dispatch error",
    )


class TestGetProjectTasks:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.get_project_tasks",
            _fake_get_project_tasks,
        )
        resp = await client.get("/evocloud/tasks/?project_id=1")
        assert resp.status_code == 200
        assert resp.json()["tasks"][0]["title"] == "T1"

    async def test_failure(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.get_project_tasks",
            _fake_get_project_tasks_fail,
        )
        resp = await client.get("/evocloud/tasks/?project_id=1")
        assert resp.status_code == 400


class TestGetTaskDetail:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.get_task_detail",
            _fake_get_task_detail,
        )
        resp = await client.get("/evocloud/tasks/1")
        assert resp.status_code == 200
        assert resp.json()["task_title"] == "Task One"

    async def test_failure(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.get_task_detail",
            _fake_get_task_detail_fail,
        )
        resp = await client.get("/evocloud/tasks/99")
        assert resp.status_code == 400


class TestCreateTask:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.create_task", _fake_create_task
        )
        resp = await client.post(
            "/evocloud/tasks/",
            json={"project_id": 1, "task_title": "New Task", "task_desc": "desc"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    async def test_failure(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.create_task", _fake_create_task_fail
        )
        resp = await client.post(
            "/evocloud/tasks/",
            json={"project_id": 1, "task_title": "New Task"},
        )
        assert resp.status_code == 400


class TestUpdateTask:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.update_task", _fake_update_task
        )
        resp = await client.put(
            "/evocloud/tasks/1",
            json={"task_title": "Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    async def test_failure(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.update_task", _fake_update_task_fail
        )
        resp = await client.put(
            "/evocloud/tasks/1",
            json={"task_title": "Updated"},
        )
        assert resp.status_code == 400


class TestDeleteTask:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.delete_task", _fake_delete_task
        )
        resp = await client.delete("/evocloud/tasks/1")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    async def test_failure(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.delete_task", _fake_delete_task_fail
        )
        resp = await client.delete("/evocloud/tasks/1")
        assert resp.status_code == 400


class TestUpdateTaskStatus:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.update_task_status",
            _fake_update_task_status,
        )
        resp = await client.put(
            "/evocloud/tasks/1/status",
            json={"status": 2, "progress": 50},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    async def test_failure(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.update_task_status",
            _fake_update_task_status_fail,
        )
        resp = await client.put(
            "/evocloud/tasks/1/status",
            json={"status": 2},
        )
        assert resp.status_code == 400


class TestExecuteTask:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.get_task_detail",
            _fake_get_task_detail,
        )
        monkeypatch.setattr(
            "app.api.routes.tasks.render_template", lambda *a, **k: "prompt"
        )
        monkeypatch.setattr(
            "app.api.routes.tasks.dispatch_agent_run", _fake_dispatch
        )
        monkeypatch.setattr(
            "app.api.routes.tasks.unique_id", lambda *a: "thread-1"
        )
        monkeypatch.setattr(
            "app.api.routes.tasks.run_agent_background", lambda *a, **k: None
        )
        resp = await client.post("/evocloud/tasks/1/execute")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["thread_id"] == "thread-1"

    async def test_task_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.get_task_detail",
            _fake_get_task_detail_fail,
        )
        resp = await client.post("/evocloud/tasks/99/execute")
        assert resp.status_code == 400

    async def test_task_data_empty(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.get_task_detail",
            _fake_get_task_detail_empty,
        )
        resp = await client.post("/evocloud/tasks/99/execute")
        assert resp.status_code == 404

    async def test_dispatch_failure(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.tasks.evocloud_manager.api.get_task_detail",
            _fake_get_task_detail,
        )
        monkeypatch.setattr(
            "app.api.routes.tasks.render_template", lambda *a, **k: "prompt"
        )
        monkeypatch.setattr(
            "app.api.routes.tasks.dispatch_agent_run", _fake_dispatch_fail
        )
        resp = await client.post("/evocloud/tasks/1/execute")
        assert resp.status_code == 500
