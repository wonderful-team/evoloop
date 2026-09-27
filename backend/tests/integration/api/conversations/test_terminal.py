"""Integration tests for conversations/terminal.py routes."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest  # noqa: F401


@pytest.fixture(autouse=True)
def _mock_hydration(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.conversations.terminal._hydrate_thread_working_directory",
        AsyncStub(None),
    )


@pytest.fixture(autouse=True)
def _mock_events(monkeypatch):
    monkeypatch.setattr("app.core.events.system_bus.publish", AsyncStub(None))
    monkeypatch.setattr(
        "app.core.monitoring.activity.activity_monitor.record_task_update",
        AsyncStub(None),
    )


@pytest.fixture(autouse=True)
def _reset_task_manager():
    from app.core.execution.terminal.background import task_manager

    task_manager._tasks.clear()
    task_manager._thread_index.clear()
    task_manager._tool_index.clear()
    task_manager._status_index.clear()
    yield


class TestRunTerminalCommand:
    async def test_execute_returns_task_id(self, client, monkeypatch):
        task = _make_task("task-1")
        monkeypatch.setattr(
            "app.api.routes.conversations.terminal.task_manager",
            SimpleNamespace(
                create_task=AsyncStub(task),
                start_task=AsyncStub(None),
                append_output_async=AsyncStub(None),
                complete_task=AsyncStub(None),
                fail_task=AsyncStub(None),
            ),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.terminal.terminal_manager",
            SimpleNamespace(run_command=lambda *a, **k: ("", "", 0)),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.terminal.ContextManager",
            SimpleNamespace(use=lambda ctx: _ctxmgr()),
        )
        loop_running = asyncio.get_event_loop()

        def _fake_create_task(coro):
            loop_running.create_task(coro)
            return asyncio.ensure_future(asyncio.sleep(0))

        monkeypatch.setattr("asyncio.create_task", _fake_create_task)
        resp = await client.post(
            "/conversations/t-1/terminal/execute",
            json={"command": "echo hello"},
        )
        assert resp.status_code == 200
        assert resp.json()["task_id"] == "task-1"

    async def test_empty_command_422(self, client, monkeypatch):
        resp = await client.post(
            "/conversations/t-1/terminal/execute",
            json={"command": "   "},
        )
        assert resp.status_code == 422

    async def test_full_execution_flow(self, client, monkeypatch):
        task = _make_task("task-1")
        created_tasks: list = []

        async def _create(req):
            created_tasks.append(req)
            return task

        async def _start(tid):
            pass

        async def _append(tid, text):
            pass

        async def _complete(tid):
            pass

        monkeypatch.setattr(
            "app.api.routes.conversations.terminal.task_manager",
            SimpleNamespace(
                create_task=_create,
                start_task=_start,
                append_output_async=_append,
                complete_task=_complete,
                fail_task=AsyncStub(None),
            ),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.terminal.terminal_manager",
            SimpleNamespace(run_command=lambda *a, **k: ("", "", 0)),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.terminal.ContextManager",
            SimpleNamespace(use=lambda ctx: _ctxmgr()),
        )
        loop_running = asyncio.get_event_loop()

        def _fake_create_task(coro):
            loop_running.create_task(coro)
            return asyncio.ensure_future(asyncio.sleep(0))

        monkeypatch.setattr("asyncio.create_task", _fake_create_task)

        resp = await client.post(
            "/conversations/t-1/terminal/execute",
            json={"command": "echo ok"},
        )
        assert resp.status_code == 200
        assert len(created_tasks) == 1
        assert created_tasks[0].task_type.value == "command"
        await asyncio.sleep(0.02)


class TestSendTerminalInput:
    async def test_input_ok(self, client, monkeypatch):
        pty = SimpleNamespace(
            _master_fd=1,
            write_raw=lambda data: None,
        )
        session = SimpleNamespace(pty=pty)

        monkeypatch.setattr(
            "app.api.routes.conversations.terminal.terminal_manager",
            SimpleNamespace(
                get_session_for_thread=lambda tid: session,
                get_session=lambda: session,
            ),
        )
        resp = await client.post(
            "/conversations/t-1/terminal/input",
            json={"text": "ls -la"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_no_session_400(self, client, monkeypatch):
        closed_pty = SimpleNamespace(_master_fd=-1, write_raw=lambda data: None)
        monkeypatch.setattr(
            "app.api.routes.conversations.terminal.terminal_manager",
            SimpleNamespace(
                get_session_for_thread=lambda tid: SimpleNamespace(pty=closed_pty),
            ),
        )
        resp = await client.post(
            "/conversations/t-1/terminal/input",
            json={"text": "ls"},
        )
        assert resp.status_code == 400


class TestGetActiveThreadTasks:
    async def test_empty(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.conversations.terminal.task_manager",
            SimpleNamespace(get_active_tasks=lambda thread_id: []),
        )
        resp = await client.get("/conversations/t-1/tasks/active")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_with_active_tasks(self, client, monkeypatch):
        task = _make_task("task-1", title="build", status_value="running")
        monkeypatch.setattr(
            "app.api.routes.conversations.terminal.task_manager",
            SimpleNamespace(get_active_tasks=lambda thread_id: [task]),
        )
        resp = await client.get("/conversations/t-1/tasks/active")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["task_id"] == "task-1"
        assert data[0]["title"] == "build"
        assert data[0]["status"] == "running"


# ---------- helpers ----------


class _CtxMgr:
    def __enter__(self):
        return None

    def __exit__(self, *_args):
        return False


def _ctxmgr():
    return _CtxMgr()


class AsyncStub:
    def __init__(self, return_value):
        self._value = return_value

    async def __call__(self, *args, **kwargs):
        return self._value


def _make_task(
    task_id: str = "task-1",
    *,
    title: str = "echo",
    status_value: str = "pending",
):
    from app.core.execution.terminal.background import TaskType

    return SimpleNamespace(
        task_id=task_id,
        task_type=TaskType.COMMAND,
        title=title,
        status=SimpleNamespace(value=status_value),
        created_at=datetime(2024, 1, 1, 0, 0, 0),
        get_recent_output=lambda limit: "",
        metadata=SimpleNamespace(model_dump=lambda: {}),
    )


@asynccontextmanager
async def _ctx(session):
    yield session
