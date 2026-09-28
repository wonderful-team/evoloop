"""队列 API 强类型契约 + task_runs 序列化回归（2026-09-23 收敛）。

- POST/PUT 请求体是 Pydantic 强类型（TaskCreateRequest/TaskEditRequest）：
  非法枚举值 → 422（此前裸 dict 静默入库——审计 P1-12）
- 队列列表内联 task_runs attempt 历史（任务与运行分离的可视面）
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.models.conversation  # noqa: F401
import app.models.project  # noqa: F401
from app.api.deps import get_current_user
from app.api.routes.tasks_queue import router as tasks_queue_router
from app.domain.tasks.service import TaskQueueService
from app.models import User
from app.models.codebase import Repository
from app.models.project import ProjectTask

OWNER_ID = 7
PROJECT_ID = 600


@pytest.fixture
async def _api_db(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.unit.db_stub import stub_db_for_loop

    engine = create_async_engine("sqlite+aiosqlite://")
    factory = stub_db_for_loop(monkeypatch, engine)

    async def _install():
        async with factory() as session:
            await session.run_sync(
                lambda sess: ProjectTask.__table__.create(
                    sess.get_bind(), checkfirst=True
                )
            )
            await session.run_sync(
                lambda sess: Repository.__table__.create(
                    sess.get_bind(), checkfirst=True
                )
            )
            from app.models.conversation import AgentActivity, Message
            from app.models.task_run import TaskRun
            from app.models.task_workflow import TaskArtifact

            await session.run_sync(
                lambda sess: TaskRun.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: TaskArtifact.__table__.create(
                    sess.get_bind(), checkfirst=True
                )
            )
            await session.run_sync(
                lambda sess: AgentActivity.__table__.create(
                    sess.get_bind(), checkfirst=True
                )
            )
            await session.run_sync(
                lambda sess: Message.__table__.create(sess.get_bind(), checkfirst=True)
            )

    await _install()
    yield factory
    await engine.dispose()


@pytest.fixture
def _single_tenant(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.tasks_queue.settings.MULTI_TENANT_MODE", False
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


@pytest.mark.usefixtures("_api_db", "_single_tenant")
class TestTypedSchemas:
    async def test_create_rejects_invalid_priority(self):
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.post(
                "/tasks/queue",
                json={"title": "t", "project_id": PROJECT_ID, "priority": "super"},
            )
        assert resp.status_code == 422

    async def test_create_rejects_invalid_risk(self):
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.post(
                "/tasks/queue",
                json={"title": "t", "project_id": PROJECT_ID, "risk_level": "T9"},
            )
        assert resp.status_code == 422

    async def test_create_rejects_recurring_without_trigger(self):
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.post(
                "/tasks/queue",
                json={"title": "t", "project_id": PROJECT_ID, "type": "recurring"},
            )
        assert resp.status_code == 422

    async def test_edit_rejects_invalid_risk(self):
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.put(
                "/tasks/queue/t-1", json={"risk_level": "T7"}
            )
        assert resp.status_code == 422

    async def test_create_accepts_valid_payload(self):
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.post(
                "/tasks/queue",
                json={
                    "title": "正常任务",
                    "project_id": PROJECT_ID,
                    "priority": "high",
                    "risk_level": "T2",
                    "dependencies": [],
                    "acceptance_criteria": ["结果可核验"],
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    async def test_create_rejects_t1_t2_without_criteria(self):
        """验收标准准入闸（fail-closed）：T1/T2 缺 acceptance_criteria → 422"""
        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.post(
                "/tasks/queue",
                json={
                    "title": "资金任务",
                    "project_id": PROJECT_ID,
                    "risk_level": "T1",
                },
            )
        assert resp.status_code == 422


@pytest.mark.usefixtures("_api_db", "_single_tenant")
class TestRunsSerialization:
    async def test_queue_list_inlines_run_history(self):
        """claim 开 run 行 → GET /queue 内联该 attempt（任务与运行分离可视面）。"""
        task = await TaskQueueService.create_task(
            project_id=PROJECT_ID,
            title="runs 可见",
            source="user",
            member_id=OWNER_ID,
        )
        claimed = await TaskQueueService.claim_for_dispatch(task.id, "wakeup_600_r1")
        assert claimed is not None

        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.get("/tasks/queue")
        assert resp.status_code == 200
        item = next(
            i for i in resp.json()["items"] if i["id"] == task.id
        )
        runs = item["runs"]
        assert len(runs) == 1
        assert runs[0]["thread_id"] == "wakeup_600_r1"
        assert runs[0]["attempt"] == 1
        assert runs[0]["status"] == "running"

    async def test_run_close_reflects_in_history(self):
        task = await TaskQueueService.create_task(
            project_id=PROJECT_ID,
            title="终态收行",
            source="user",
            member_id=OWNER_ID,
        )
        await TaskQueueService.claim_for_dispatch(task.id, "wakeup_600_r2")
        await TaskQueueService.advance_task(
            task.id, "failed", result="boom", thread_id="wakeup_600_r2", by="system"
        )

        async with _client(_make_app(as_user=OWNER_ID)) as client:
            resp = await client.get("/tasks/queue")
        item = next(i for i in resp.json()["items"] if i["id"] == task.id)
        assert item["runs"][0]["status"] == "failed"
        assert "boom" in (item["runs"][0]["error_message"] or "")
