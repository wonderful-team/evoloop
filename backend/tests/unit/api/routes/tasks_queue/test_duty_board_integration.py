from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.models.conversation  # noqa: F401
import app.models.planning  # noqa: F401
import app.models.project  # noqa: F401
from app.api.deps import get_current_user
from app.api.routes.conversations import messages as conversation_messages_router
from app.api.routes.planning import router as planning_router
from app.api.routes.stream import router as stream_router
from app.api.routes.tasks_queue import router as tasks_queue_router
from app.domain.tasks.events import publish_task_queue_event
from app.domain.tasks.service import TaskQueueService
from app.infrastructure.database.sql.database import session_scope
from app.models import User
from app.models.codebase import Repository
from app.models.conversation import (
    AgentActivity,
    Conversation,
    HumanRequest,
    Message,
    MessageReference,
    ThreadSequence,
)
from app.models.file_operation import FileOperation
from app.models.planning import Plan, PlanStep

OWNER_ID = 21
PROJECT_ID = 501
THREAD_ID = "duty-thread-501"


@pytest.fixture
async def _board_db(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.models.project import ProjectTask
    from tests.unit.db_stub import stub_db_for_loop

    engine = create_async_engine("sqlite+aiosqlite://")
    factory = stub_db_for_loop(monkeypatch, engine)
    try:

        async with factory() as session:
            bind = session.get_bind()
            await session.run_sync(lambda _: ProjectTask.__table__.create(bind, checkfirst=True))
            await session.run_sync(lambda _: Repository.__table__.create(bind, checkfirst=True))
            await session.run_sync(lambda _: Conversation.__table__.create(bind, checkfirst=True))
            await session.run_sync(lambda _: AgentActivity.__table__.create(bind, checkfirst=True))
            await session.run_sync(lambda _: HumanRequest.__table__.create(bind, checkfirst=True))
            await session.run_sync(lambda _: ThreadSequence.__table__.create(bind, checkfirst=True))
            await session.run_sync(lambda _: Message.__table__.create(bind, checkfirst=True))
            await session.run_sync(lambda _: MessageReference.__table__.create(bind, checkfirst=True))
            await session.run_sync(lambda _: FileOperation.__table__.create(bind, checkfirst=True))
            await session.run_sync(lambda _: Plan.__table__.create(bind, checkfirst=True))
            await session.run_sync(lambda _: PlanStep.__table__.create(bind, checkfirst=True))
            from app.models.task_run import TaskRun
            from app.models.task_workflow import TaskArtifact, TaskWorkflow

            await session.run_sync(lambda _: TaskWorkflow.__table__.create(bind, checkfirst=True))
            await session.run_sync(lambda _: TaskArtifact.__table__.create(bind, checkfirst=True))
            await session.run_sync(lambda _: TaskRun.__table__.create(bind, checkfirst=True))

        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def _single_tenant(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.tasks_queue.settings.MULTI_TENANT_MODE",
        False,
    )


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(tasks_queue_router, prefix="/tasks")
    app.include_router(planning_router, prefix="/planning")
    app.include_router(conversation_messages_router.router, prefix="/conversations")
    app.include_router(stream_router)
    app.dependency_overrides[get_current_user] = lambda: User(
        id=OWNER_ID, is_active=True
    )
    return app


async def _seed_project() -> None:
    async with session_scope() as session:
        session.add(
            Repository(
                project_id=PROJECT_ID,
                member_id=OWNER_ID,
                name="duty-integration",
                url="https://example.com/duty-integration.git",
                sync_status="DETECTED",
                indexing_status="pending",
            )
        )


async def _seed_run_data(task_id: str) -> None:
    async with session_scope() as session:
        session.add_all(
            [
                Conversation(id=THREAD_ID, project_id=PROJECT_ID, member_id=OWNER_ID),
                AgentActivity(
                    thread_id=THREAD_ID,
                    status="running",
                    main_goal="Run duty integration",
                    llm_calls=4,
                    input_tokens=1200,
                    output_tokens=800,
                ),
                Plan(
                    id="plan-501",
                    thread_id=THREAD_ID,
                    task_id=task_id,
                    title="Duty integration plan",
                    status="active",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                PlanStep(
                    id="step-1",
                    plan_id="plan-501",
                    title="Inspect market",
                    status="completed",
                    result="3 opportunities",
                    order=1,
                ),
                PlanStep(
                    id="step-2",
                    plan_id="plan-501",
                    title="Draft brief",
                    status="in_progress",
                    order=2,
                ),
                Message(
                    id="msg-task-start",
                    thread_id=THREAD_ID,
                    member_id=OWNER_ID,
                    project_id=PROJECT_ID,
                    role="human",
                    content="Start the autonomous selection task",
                    sequence_number=1,
                    is_visible=True,
                    status="completed",
                ),
                Message(
                    id="msg-task-tool",
                    thread_id=THREAD_ID,
                    member_id=OWNER_ID,
                    project_id=PROJECT_ID,
                    role="tool",
                    tool_name="market_research",
                    content="已生成市场扫描摘要：3 个候选机会",
                    sequence_number=2,
                    is_visible=True,
                    action_type="tool_output",
                    category="tool_output",
                    run_id="run-501",
                    status="completed",
                ),
                Message(
                    id="msg-task-final",
                    thread_id=THREAD_ID,
                    member_id=OWNER_ID,
                    project_id=PROJECT_ID,
                    role="ai",
                    content="已完成第一轮调研，正在整理选品简报。",
                    sequence_number=3,
                    is_visible=True,
                    run_id="run-501",
                    status="completed",
                ),
            ]
        )


@pytest.mark.usefixtures("_board_db", "_single_tenant")
async def test_autonomous_duty_board_full_data_chain():
    await _seed_project()
    async with AsyncClient(
        transport=ASGITransport(app=_app()), base_url="http://test"
    ) as client:
        created = await client.post(
            "/tasks/queue",
            json={"title": "Autonomous duty run", "project_id": PROJECT_ID},
        )
        assert created.status_code == 200
        task_id = created.json()["id"]

        task = await TaskQueueService.take_task(task_id, THREAD_ID)
        assert task.status == "in_progress"
        assert task.last_thread_id == THREAD_ID
        await _seed_run_data(task_id)

        queue = await client.get("/tasks/queue", params={"project_id": PROJECT_ID})
        assert queue.status_code == 200
        items = queue.json()["items"]
        assert [item["id"] for item in items] == [task_id]
        assert items[0]["status"] == "in_progress"
        assert items[0]["last_thread_id"] == THREAD_ID

        plan = await client.get(f"/planning/conversations/{THREAD_ID}/plan")
        assert plan.status_code == 200
        plan_body = plan.json()
        assert plan_body["status"] == "success"
        assert plan_body["plan"]["title"] == "Duty integration plan"
        assert [step["status"] for step in plan_body["plan"]["steps"]] == [
            "completed",
            "in_progress",
        ]

        messages = await client.get(
            f"/conversations/{THREAD_ID}/messages",
            params={"limit": 40, "include_tool_calls": True},
        )
        assert messages.status_code == 200
        message_body = messages.json()
        assert message_body["total_count"] >= 1, message_body
        serialized_messages = json.dumps(message_body, ensure_ascii=False)
        assert "已生成市场扫描摘要" in serialized_messages
        assert "已完成第一轮调研" in serialized_messages

        dashboard = await client.get(
            "/tasks/queue/dashboard", params={"project_id": PROJECT_ID}
        )
        assert dashboard.status_code == 200
        board = dashboard.json()
        assert board["counts"]["in_progress"] == 1
        assert board["duty_state"] == "busy"
        assert board["tokens"]["today"]["input"] == 1200
        assert board["tokens"]["today"]["output"] == 800
        assert board["tokens"]["today"]["llm_calls"] == 4
        assert board["current_run"]["thread_id"] == THREAD_ID
        assert board["current_run"]["input_tokens"] == 1200

        sse_messages: asyncio.Queue[dict] = asyncio.Queue()
        disconnect_event = asyncio.Event()

        async def _send(message: dict) -> None:
            await sse_messages.put(message)

        async def _receive() -> dict:
            await disconnect_event.wait()
            return {"type": "http.disconnect"}

        sse_scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/stream/tasks",
            "raw_path": b"/stream/tasks",
            "query_string": f"project_id={PROJECT_ID}".encode(),
            "root_path": "",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "headers": [],
        }
        sse_task = asyncio.create_task(_app()(sse_scope, _receive, _send))
        response_start = await asyncio.wait_for(sse_messages.get(), timeout=5)
        assert response_start["type"] == "http.response.start"
        assert response_start["status"] == 200

        stream_text = ""
        while '"event": "connected"' not in stream_text:
            response_body = await asyncio.wait_for(sse_messages.get(), timeout=5)
            assert response_body["type"] == "http.response.body"
            stream_text += response_body["body"].decode()

        await publish_task_queue_event(task, event="task_created")
        while '"event": "task_created"' not in stream_text:
            response_body = await asyncio.wait_for(sse_messages.get(), timeout=5)
            assert response_body["type"] == "http.response.body"
            stream_text += response_body["body"].decode()

        disconnect_event.set()

        sse_task.cancel()
        try:
            await sse_task
        except asyncio.CancelledError:
            pass
        assert '"event": "connected"' in stream_text
        assert '"event": "task_created"' in stream_text
