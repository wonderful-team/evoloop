"""Semi-real voice route pipeline.

Real: retriever, RouteIndex (on-disk lancedb), router (parse/degrade logic),
voice_ws._handle_route, executor, MacroEngine, and a real SQLite DB.
Stubbed at true external boundaries only: embedding model, route LLM, WS
connection manager, idempotency store.
"""

import asyncio

import pytest

fastapi = pytest.importorskip("fastapi")  # noqa: F401

from app.api.routes import voice_ws  # noqa: E402
from app.core.routing import executor, retriever  # noqa: E402
from app.core.routing import router as route_router  # noqa: E402
from app.core.routing.index import RouteIndex  # noqa: E402
from app.infrastructure.database import session_scope  # noqa: E402
from app.models.learning import LearnedSkill  # noqa: E402
from app.models.macro import Macro  # noqa: E402

_VEC = [0.1] * 8


class _FakeEmbedder:
    async def embed_query(self, _text: str) -> list[float]:
        return list(_VEC)


class _FakeManager:
    def __init__(self):
        self.bound: list[tuple[str, str]] = []
        self.pushes: list[tuple[str, dict]] = []

    async def bind_thread(self, tid, cid):
        self.bound.append((tid, cid))

    async def push(self, tid, env):
        self.pushes.append((tid, env))
        return True

    async def record_terminal_result(self, message_id, body):
        pass


class _Msg:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.content = ""


class _Runnable:
    def __init__(self, msg):
        self._msg = msg

    async def ainvoke(self, _prompt):
        return self._msg


class _FakeLLM:
    def __init__(self, msg):
        self._msg = msg

    def bind_tools(self, _tools, tool_choice=None):
        return _Runnable(self._msg)


@pytest.fixture
def route_index(tmp_path, monkeypatch):
    idx = RouteIndex(str(tmp_path / "v"), dim=8)
    monkeypatch.setattr(retriever, "_get_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(retriever, "get_index", lambda: idx)
    return idx


def _patch_llm(monkeypatch, tool_calls):
    async def _create():
        return _FakeLLM(_Msg(tool_calls))

    monkeypatch.setattr(route_router, "_create_route_llm", _create)


def _patch_ws(monkeypatch, fake):
    monkeypatch.setattr(voice_ws, "manager", fake)
    monkeypatch.setattr(executor, "manager", fake)

    async def _nodup(_message_id, _ttl=300):
        return False

    monkeypatch.setattr(voice_ws, "is_duplicate", _nodup)


async def _drain():
    for _ in range(10):
        await asyncio.sleep(0)


async def _wait_for(fake: _FakeManager, status: str, timeout: float = 5.0):
    """Poll until a push with the given status arrives (fire-and-forget tasks
    need several event-loop passes through aiosqlite's worker thread)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if any(env["body"]["status"] == status for _, env in fake.pushes):
            return
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_full_route_to_done_semi_real(_real_db, route_index, monkeypatch):
    # Real DB skill + matching index entry (identical vectors -> top score).
    async with session_scope() as db:
        skill = LearnedSkill(
            id=42,
            name="播放音乐",
            description="播放歌曲",
            trigger_patterns="[]",
            parameters="[]",
            status="verified",
            is_active=True,
        )
        macro = Macro(
            name="播放音乐",
            description="播放歌曲",
            trigger_patterns="[]",
            parameters="[]",
            macro_script="steps: []",
            status="verified",
            is_active=True,
        )
        db.add(skill)
        db.add(macro)
        await db.flush()
        skill.macro_id = macro.id
        await db.flush()
    route_index.upsert(
        [
            {
                "id": "skill:42",
                "type": "skill",
                "name": "播放音乐",
                "description": "播放歌曲",
                "params_schema": {},
                "target": "42",
            }
        ],
        [list(_VEC)],
    )
    _patch_llm(
        monkeypatch,
        [
            {
                "name": "execute_skill",
                "args": {"skill_id": 42, "params": {"song": "晴天"}},
            }
        ],
    )
    fake = _FakeManager()
    _patch_ws(monkeypatch, fake)

    await voice_ws._handle_route(
        {
            "text": "播放周杰伦的晴天",
            "thread_id": "thread-e2e",
            "message_id": "msg-e2e",
        },
        "conn-e2e",
    )
    await _wait_for(fake, "done")

    statuses = [env["body"]["status"] for _, env in fake.pushes]
    assert statuses == ["routed", "done"]
    routed = fake.pushes[0][1]["body"]
    assert routed["target"]["type"] == "skill"
    assert routed["target"]["id"] == 42
    # Candidates come from the real retriever + real router.
    assert routed["candidates"][0]["id"] == "skill:42"
    done = fake.pushes[1][1]["body"]
    assert done["thread_id"] == "thread-e2e"


@pytest.mark.asyncio
async def test_local_has_no_server_done_semi_real(route_index, monkeypatch):
    route_index.upsert(
        [
            {
                "id": "local:open_app",
                "type": "local",
                "name": "open_app",
                "description": "打开应用",
                "params_schema": {"app": "str"},
                "target": "open_app",
            }
        ],
        [list(_VEC)],
    )
    _patch_llm(
        monkeypatch,
        [
            {
                "name": "local_action",
                "args": {"action": "open_app", "params": {"app": "微信"}},
            }
        ],
    )
    fake = _FakeManager()
    _patch_ws(monkeypatch, fake)

    await voice_ws._handle_route(
        {"text": "打开微信", "thread_id": "thread-local", "message_id": "msg-local"},
        "conn-local",
    )
    await _drain()

    statuses = [env["body"]["status"] for _, env in fake.pushes]
    assert statuses == ["routed"]
    assert fake.pushes[0][1]["body"]["target"]["type"] == "local"


@pytest.mark.asyncio
async def test_unconfirmed_skill_never_reaches_router_semi_real(
    _real_db, route_index, monkeypatch
):
    # A pending_review skill is in the DB but NOT in the route index (status
    # gate). The router must delegate instead of executing it.
    async with session_scope() as db:
        db.add(
            LearnedSkill(
                id=43,
                name="未确认技能",
                description="不该被路由",
                trigger_patterns="[]",
                parameters="[]",
                status="pending_review",
                is_active=True,
            )
        )
        await db.flush()
    route_index.upsert(
        [
            {
                "id": "agent:default",
                "type": "agent",
                "name": "Agent 兜底",
                "description": "复杂任务交给 Agent",
                "params_schema": {"task": "str"},
                "target": "default",
            }
        ],
        [list(_VEC)],
    )

    # Retrieval hits only the agent fallback entry; the real router must
    # delegate (LLM chooses delegate) and never touch the unconfirmed skill.
    _patch_llm(
        monkeypatch,
        [{"name": "delegate", "args": {"task": "执行未确认技能"}}],
    )
    executed = []

    async def _spy_execute(tid, decision):
        executed.append((tid, decision))

    monkeypatch.setattr(executor, "execute", _spy_execute)
    fake = _FakeManager()
    _patch_ws(monkeypatch, fake)

    await voice_ws._handle_route(
        {
            "text": "执行未确认技能",
            "thread_id": "thread-gate",
            "message_id": "msg-gate",
        },
        "conn-gate",
    )
    await _drain()

    # Delegation is reported as routed/agent (design §8.2); the unconfirmed
    # skill itself is never handed to the executor.
    assert len(fake.pushes) == 1
    body = fake.pushes[0][1]["body"]
    assert body["status"] == "routed"
    assert body["target"]["type"] == "agent"
    assert len(executed) == 1
    assert executed[0][1].target_type == "agent"
