"""DB 并发 abort 压力测试（生产同构：文件库 + QueuePool + WAL/busy_timeout）。

用法：``.venv/bin/python scripts/db_abort_stress.py``
验收：P2 除 cancelled 外 other=0；settle 后 leaked_fairies=0；P3 全 200。
依赖 tests/unit/db_stub 与 pool_leak_probe（自动开启 EVOLOOP_POOL_LEAK_PROBE）。

P1 基线：30 并发混合读写
P2 abort 风暴：150 并发，~60% 在早期被 cancel（打中 checkout/execute/close 窗口）
P3 风暴后健康：串行请求 100% 成功；pool 归零；per-fairy 追踪器报告泄漏数
"""
import asyncio
import gc
import logging
import os
import random
import tempfile
from collections import Counter
from pathlib import Path

os.environ["EVOLOOP_POOL_LEAK_PROBE"] = "1"
os.environ["EVOLOOP_POOL_LEAK_PROBE_LINGER"] = "999"
os.environ["EVOLOOP_POOL_LEAK_PROBE_GC_INTERVAL"] = "600"
logging.disable(logging.CRITICAL)

from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

THREAD = "stress-thread"

class _MP:
    def setattr(self, o, a, v): setattr(o, a, v)

async def build():
    from app.infrastructure.database.pool_leak_probe import maybe_install
    from tests.unit.db_stub import stub_db_for_loop
    tmp = Path(tempfile.mkdtemp())
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp}/stress.db", pool_size=5, max_overflow=10, pool_timeout=30
    )
    maybe_install(engine)
    from app.infrastructure.database.resource_manager import DatabaseResourceManager
    DatabaseResourceManager._setup_sqlite_pragmas(engine)  # 生产同构：WAL + busy_timeout=30s
    stub_db_for_loop(_MP(), engine)

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
    from app.models.project import ProjectTask
    from app.models.task_workflow import TaskArtifact, TaskWorkflow
    TABLES = [ProjectTask, Repository, Conversation, Message, MessageReference, ThreadSequence,
              AgentActivity, HumanRequest, FileOperation, Plan, PlanStep, TaskWorkflow, TaskArtifact]
    async with engine.begin() as conn:
        for t in TABLES:
            await conn.run_sync(lambda sess, _t=t: _t.__table__.create(sess, checkfirst=True))

    from fastapi import FastAPI

    from app.api.deps import get_current_user
    from app.api.routes.conversations import messages as cmsg
    from app.api.routes.planning import router as plan_r
    from app.api.routes.tasks_queue import router as tq
    from app.models import User
    app = FastAPI()
    app.include_router(tq, prefix="/tasks")
    app.include_router(plan_r, prefix="/planning")
    app.include_router(cmsg.router, prefix="/conversations")
    app.dependency_overrides[get_current_user] = lambda: User(id=1, is_active=True)

    from app.infrastructure.database import session_scope
    async with session_scope() as s:
        s.add(Conversation(id=THREAD, project_id=9, title="t", member_id=1))
        for i in range(10):
            s.add(Message(id=f"sm{i}", thread_id=THREAD, content=f"c{i}", role="ai",
                          category="assistant_response", sequence_number=i + 1,
                          is_visible=True, status="completed"))
    return engine, app

def pool_state(engine):
    p = engine.pool
    return f"checkedout={p.checkedout()} overflow={p.overflow()}"

RESP_TEXT = {}
async def one_request(client, i):
    if i % 3 == 0:
        r = await client.post("/tasks/queue", json={"title": f"t{i}", "project_id": 9, "description": "d"})
    elif i % 3 == 1:
        r = await client.get(f"/conversations/{THREAD}/messages?limit=40&include_tool_calls=true")
    else:
        r = await client.get("/tasks/queue/dashboard")
    if r.status_code != 200:
        RESP_TEXT.setdefault(r.status_code, (r.request.url.path, r.text[:150]))
    return r.status_code

async def main():
    from httpx import ASGITransport, AsyncClient

    from app.infrastructure.database.pool_leak_probe import _fairy_watch, _records
    engine, app = await build()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        rs = await asyncio.gather(*(one_request(client, i) for i in range(30)), return_exceptions=True)
        ok = sum(1 for x in rs if x == 200)
        print(f"P1 baseline 30 concurrent: ok200={ok} err={len(rs)-ok}  {pool_state(engine)}")

        random.seed(42)
        tasks = [asyncio.create_task(one_request(client, 100 + i)) for i in range(400)]
        await asyncio.sleep(0.005)
        early = [t for t in tasks if random.random() < 0.3]   # 早期：checkout 排队/执行中
        for t in early:
            t.cancel()
        await asyncio.sleep(0.15)
        late = [t for t in tasks if not t.done() and random.random() < 0.35]  # 晚期：commit/close 窗口
        for t in late:
            t.cancel()
        to_cancel = early + late
        results = await asyncio.gather(*tasks, return_exceptions=True)
        done_ok = sum(1 for r in results if r == 200)
        canceled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
        others = [r for r in results if r != 200 and not isinstance(r, asyncio.CancelledError)]
        print(f"P2 storm 150 ({len(to_cancel)} cancelled): ok200={done_ok} cancelled={canceled} other={len(others)}  {pool_state(engine)}")
        print("P2 other kinds:", Counter((x if isinstance(x, int) else type(x).__name__) for x in others).most_common(6))
        for code, (path, text) in sorted(RESP_TEXT.items()):
            print(f"  HTTP {code} @ {path}: {text}")

        for _ in range(10):
            await asyncio.sleep(0.1)
            gc.collect()
        print(f"after settle: leaked_fairies={len(_fairy_watch)} outstanding={len(_records)}  {pool_state(engine)}")
        if _fairy_watch:
            for e in _fairy_watch.values():
                print("--- LEAKED BORROWER STACK ---\n" + e["stack"][:1500])

        rs = await asyncio.gather(*(one_request(client, 500 + i) for i in range(20)), return_exceptions=True)
        ok = sum(1 for x in rs if x == 200)
        print(f"P3 post-storm 20 requests: ok200={ok}/20  final {pool_state(engine)}")
        print("P3 failures:", Counter(str(x)[:100] for x in rs if x != 200).most_common(3))
    await engine.dispose()

asyncio.run(main())
print("STRESS DONE")
