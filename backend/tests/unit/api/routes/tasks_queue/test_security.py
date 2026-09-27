"""Task queue API security tests — auth, ownership isolation, member attribution.

Covers tasks_queue.py guards added for multi-tenant safety:
- unauthenticated requests -> 401 (CurrentUser dependency)
- create_task writes the caller's member_id onto the task
- accessing another member's task -> 404 (edit / confirm / accept / reject)
- creating a task in a project owned by another member -> 404
- dashboard with a project_id owned by another member -> 404

NOTE (known gap, asserted here to pin current behavior): GET /queue/dashboard
without project_id aggregates across ALL members' tasks (auth-only, no
per-member filtering). Cross-user aggregation risk in multi-tenant mode is a
documented follow-up; this test documents the current contract.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

import app.models.conversation  # noqa: F401
import app.models.project  # noqa: F401
from app.api.deps import get_current_user, get_current_user_optional
from app.api.routes.stream import router as stream_router
from app.api.routes.tasks_queue import router as tasks_queue_router
from app.domain.tasks.service import TaskQueueService
from app.infrastructure.database.sql.database import session_scope
from app.models import User
from app.models.codebase import Repository
from app.models.conversation import AgentActivity, HumanRequest
from app.models.project import ProjectTask
from app.models.task_workflow import TaskWorkflow

OWNER_ID = 7
FOREIGN_ID = 9
PROJECT_ID = 500


@pytest.fixture
async def _api_db(monkeypatch):
    """In-memory aiosqlite engine patched into db_resource_manager."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.unit.db_stub import stub_db_for_loop

    engine = create_async_engine("sqlite+aiosqlite://")
    factory = stub_db_for_loop(monkeypatch, engine)
    async with factory() as session:
        await session.run_sync(
            lambda sess: ProjectTask.__table__.create(sess.get_bind(), checkfirst=True)
        )
        await session.run_sync(
            lambda sess: Repository.__table__.create(sess.get_bind(), checkfirst=True)
        )
        await session.run_sync(
            lambda sess: TaskWorkflow.__table__.create(sess.get_bind(), checkfirst=True)
        )
        await session.run_sync(
            lambda sess: AgentActivity.__table__.create(
                sess.get_bind(), checkfirst=True
            )
        )
        await session.run_sync(
            lambda sess: HumanRequest.__table__.create(
                sess.get_bind(), checkfirst=True
            )
        )
    yield factory
    await engine.dispose()


@pytest.fixture
def _multi_tenant(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.tasks_queue.settings.MULTI_TENANT_MODE", True
    )


def _make_app(as_user: int | None) -> FastAPI:
    app = FastAPI()
    app.include_router(tasks_queue_router, prefix="/tasks")
    if as_user is not None:
        app.dependency_overrides[get_current_user] = lambda: User(
            id=as_user, is_active=True
        )
    return app


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_repository(project_id: int, member_id: int) -> None:
    async with session_scope() as session:
        session.add(
            Repository(
                project_id=project_id,
                member_id=member_id,
                name=f"repo-{project_id}",
                url=f"https://example.com/repo-{project_id}.git",
                sync_status="DETECTED",
                indexing_status="pending",
            )
        )


async def _seed_workflow(
    workflow_id: str,
    project_id: int,
    member_id: int,
    *,
    status: str = "completed",
) -> None:
    async with session_scope() as session:
        session.add(
            TaskWorkflow(
                id=workflow_id,
                project_id=project_id,
                member_id=member_id,
                title=f"workflow-{project_id}",
                goal="test",
                status=status,
                inputs={},
            )
        )


async def _get_workflow(workflow_id: str) -> TaskWorkflow | None:
    async with session_scope() as session:
        result = await session.execute(
            select(TaskWorkflow).where(TaskWorkflow.id == workflow_id)
        )
        return result.scalar_one_or_none()


@pytest.mark.usefixtures("_api_db", "_multi_tenant")
class TestAuthRequired:
    async def test_create_task_without_token_returns_401(self):
        async with _client(_make_app(as_user=None)) as client:
            resp = await client.post(
                "/tasks/queue", json={"title": "t", "project_id": PROJECT_ID}
            )
        assert resp.status_code == 401

    async def test_list_queue_without_token_returns_401(self):
        async with _client(_make_app(as_user=None)) as client:
            resp = await client.get("/tasks/queue")
        assert resp.status_code == 401

    async def test_list_workflows_without_token_returns_401(self):
        async with _client(_make_app(as_user=None)) as client:
            resp = await client.get(
                "/tasks/workflows", params={"project_id": PROJECT_ID}
            )
        assert resp.status_code == 401

    async def test_workflow_stream_without_token_returns_401(self):
        app = FastAPI()
        app.include_router(stream_router)
        async with _client(app) as client:
            resp = await client.get("/stream/workflow/missing")
        assert resp.status_code == 401


@pytest.mark.usefixtures("_api_db", "_multi_tenant")
class TestMemberAttribution:
    async def test_create_task_writes_current_user_member_id(self):
        await _seed_repository(PROJECT_ID, OWNER_ID)
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.post(
                "/tasks/queue", json={"title": "t", "project_id": PROJECT_ID}
            )
        assert resp.status_code == 200
        task = await TaskQueueService.get_task(resp.json()["id"])
        assert task.member_id == OWNER_ID


@pytest.mark.usefixtures("_api_db", "_multi_tenant")
class TestOwnershipIsolation:
    async def _seed_foreign_task(self) -> str:
        task = await TaskQueueService.create_task(
            project_id=PROJECT_ID,
            title="foreign",
            source="user",
            member_id=FOREIGN_ID,
        )
        return task.id

    async def test_edit_foreign_task_returns_404(self):
        task_id = await self._seed_foreign_task()
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.put(
                f"/tasks/queue/{task_id}", json={"title": "hijack"}
            )
        assert resp.status_code == 404

    async def test_confirm_foreign_task_returns_404(self):
        task_id = await self._seed_foreign_task()
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.post(f"/tasks/queue/{task_id}/confirm")
        assert resp.status_code == 404

    async def test_accept_foreign_task_returns_404(self):
        task_id = await self._seed_foreign_task()
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.post(f"/tasks/queue/{task_id}/accept")
        assert resp.status_code == 404

    async def test_reject_foreign_task_returns_404(self):
        task_id = await self._seed_foreign_task()
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.post(
                f"/tasks/queue/{task_id}/reject", json={"feedback": "nope"}
            )
        assert resp.status_code == 404

    async def test_create_task_in_foreign_project_returns_404(self):
        await _seed_repository(PROJECT_ID, FOREIGN_ID)
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.post(
                "/tasks/queue", json={"title": "t", "project_id": PROJECT_ID}
            )
        assert resp.status_code == 404

    async def test_dashboard_foreign_project_returns_404(self):
        await _seed_repository(PROJECT_ID, FOREIGN_ID)
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.get(
                "/tasks/queue/dashboard", params={"project_id": PROJECT_ID}
        )
        assert resp.status_code == 404

    async def test_accept_refreshes_workflow_status(self):
        await _seed_repository(PROJECT_ID, OWNER_ID)
        await _seed_workflow(
            "workflow-accept", PROJECT_ID, OWNER_ID, status="running"
        )
        task = await TaskQueueService.create_task(
            project_id=PROJECT_ID,
            title="accept workflow",
            source="user",
            member_id=OWNER_ID,
        )
        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(ProjectTask.id == task.id)
                .values(
                    status="waiting_acceptance",
                    workflow_id="workflow-accept",
                    last_result="workflow stage done",
                )
            )

        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.post(f"/tasks/queue/{task.id}/accept")

        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"
        workflow = await _get_workflow("workflow-accept")
        assert workflow is not None
        assert workflow.status == "completed"

    async def test_reject_refreshes_workflow_status(self):
        await _seed_repository(PROJECT_ID, OWNER_ID)
        await _seed_workflow(
            "workflow-reject",
            PROJECT_ID,
            OWNER_ID,
            status="waiting_acceptance",
        )
        task = await TaskQueueService.create_task(
            project_id=PROJECT_ID,
            title="reject workflow",
            source="user",
            member_id=OWNER_ID,
        )
        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(ProjectTask.id == task.id)
                .values(
                    status="waiting_acceptance",
                    workflow_id="workflow-reject",
                    last_result="workflow stage done",
                )
            )

        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.post(
                f"/tasks/queue/{task.id}/reject",
                json={"feedback": "needs rework"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        workflow = await _get_workflow("workflow-reject")
        assert workflow is not None
        assert workflow.status == "running"

    async def test_dashboard_without_project_id_scopes_to_member(self):
        """No project_id -> member-scoped aggregation (isolation, was a known gap)."""
        await TaskQueueService.create_task(
            project_id=PROJECT_ID,
            title="foreign-task",
            source="user",
            member_id=FOREIGN_ID,
        )
        await _seed_repository(PROJECT_ID, FOREIGN_ID)
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.get("/tasks/queue/dashboard")
        assert resp.status_code == 200
        assert resp.json()["counts"].get("pending") is None

    async def test_hitl_pending_drops_foreign_member_requests(self):
        """hitl-pending fail-closed: foreign-member requests are not exposed."""
        from app.models.conversation import HumanRequest as HR

        task = await TaskQueueService.create_task(
            project_id=PROJECT_ID,
            title="foreign hitl",
            source="user",
            member_id=FOREIGN_ID,
        )
        await _seed_repository(PROJECT_ID, FOREIGN_ID)
        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(ProjectTask.id == task.id)
                .values(status="in_progress", last_thread_id="wakeup_500_hitl")
            )
            session.add(
                HR(
                    id="hr-foreign-1",
                    thread_id="wakeup_500_hitl",
                    type="confirmation",
                    description="approve refund?",
                    status="pending",
                )
            )
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.get("/tasks/queue/hitl-pending")
        assert resp.status_code == 200
        ids = [i["request_id"] for i in resp.json()["items"]]
        assert "hr-foreign-1" not in ids

    async def test_list_workflows_in_foreign_project_returns_404(self):
        await _seed_repository(PROJECT_ID, FOREIGN_ID)
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.get(
                "/tasks/workflows", params={"project_id": PROJECT_ID}
            )
        assert resp.status_code == 404

    async def test_list_workflows_returns_project_history(self):
        await _seed_repository(PROJECT_ID, OWNER_ID)
        await _seed_workflow("workflow-500", PROJECT_ID, OWNER_ID)
        await _seed_workflow("workflow-501", 501, OWNER_ID)

        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.get(
                "/tasks/workflows", params={"project_id": PROJECT_ID}
            )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert payload["count"] == 1
        assert payload["items"][0]["id"] == "workflow-500"

    async def test_workflow_stream_rejects_foreign_project(self):
        await _seed_repository(PROJECT_ID, OWNER_ID)
        await _seed_workflow("workflow-foreign", PROJECT_ID, OWNER_ID)

        app = FastAPI()
        app.include_router(stream_router)
        app.dependency_overrides[get_current_user_optional] = lambda: User(
            id=FOREIGN_ID, is_active=True
        )
        async with _client(app) as client:
            resp = await client.get("/stream/workflow/workflow-foreign")
        assert resp.status_code == 404

    async def test_workflow_stream_closes_for_completed_workflow(self):
        await _seed_repository(PROJECT_ID, OWNER_ID)
        await _seed_workflow("workflow-done", PROJECT_ID, OWNER_ID)

        app = FastAPI()
        app.include_router(stream_router)
        app.dependency_overrides[get_current_user_optional] = lambda: User(
            id=OWNER_ID, is_active=True
        )
        async with _client(app) as client:
            resp = await client.get("/stream/workflow/workflow-done")

        assert resp.status_code == 200
        assert "event: workflow_updated" in resp.text
        assert '"event": "connected"' in resp.text
