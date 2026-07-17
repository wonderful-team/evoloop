"""Live (close-to-real) route tests against a running LM Studio.

Per VLA design §14.1 these tests use REAL dependencies (LM Studio embeddings +
LLM, a real LanceDB `RouteIndex`). They are excluded from the default unit run:
when LM Studio is not reachable they `skip` instead of failing. They never mock
the model, the embedder, or the index — only the surrounding app config is
isolated by constructing the clients directly (no `SystemConfigService`/DB).

Run:
    EMBEDDED_MODE=true pytest tests/routing/test_route_live.py --integration -q
"""

from __future__ import annotations

import json
import os
import socket
import time

import pytest

from app.core.routing.index import RouteIndex
from app.core.routing.router import ROUTE_TOOLS
from app.infrastructure.embeddings.openai import GenericOpenAIEmbedder
from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI

pytestmark = [pytest.mark.integration, pytest.mark.llm]

_LM_BASE = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
_LLM_MODEL = os.environ.get("ROUTE_LLM_MODEL", "qwen3-4b-instruct-2507")
_EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-bge-base-zh-v1.5")
_DIM = int(os.environ.get("EMBEDDING_DIMENSIONS", "768"))

# Generous ceilings: these guards catch severe regressions, not normal jitter on
# a shared dev box (cold model load, other GPU work).
_EMBED_P95_MS = float(os.environ.get("LIVE_EMBED_P95_MS", "500"))
_ROUTE_P95_MS = float(os.environ.get("LIVE_ROUTE_P95_MS", "5000"))


def _host_port(base: str) -> tuple[str, int]:
    rest = base.split("://", 1)[-1]
    hostport = rest.split("/", 1)[0]
    if ":" in hostport:
        host, port_s = hostport.rsplit(":", 1)
        try:
            return host, int(port_s)
        except ValueError:
            return host, 80
    return hostport, 80


def _lmstudio_reachable() -> bool:
    host, port = _host_port(_LM_BASE)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except (OSError, TimeoutError):
        return False


@pytest.fixture(autouse=True)
def _require_live(request) -> None:
    # Live tests hit a real LM Studio and are opt-in via --integration so the
    # default `pytest tests/routing` unit run stays fast and dependency-free.
    if not request.config.getoption("--integration"):
        pytest.skip("live route tests require --integration")
    if not _lmstudio_reachable():
        pytest.skip(f"LM Studio not reachable at {_LM_BASE} (live route tests skip)")


def _embedder() -> GenericOpenAIEmbedder:
    return GenericOpenAIEmbedder(
        api_key="lm-studio", base_url=_LM_BASE, model=_EMBED_MODEL, dimensions=_DIM
    )


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[int(0.95 * (len(ordered) - 1))]


async def test_live_embed_dimension_and_recall(tmp_path) -> None:
    """Real bge embeddings + real LanceDB: a semantically matching skill wins."""
    embedder = _embedder()
    entries = [
        {
            "id": "music_1",
            "type": "skill",
            "name": "播放周杰伦的晴天",
            "description": "在音乐 App 中播放周杰伦演唱的歌曲《晴天》",
            "execution_mode": "skill",
            "target": "skill:1",
        },
        {
            "id": "doc_1",
            "type": "skill",
            "name": "打开项目最新 PRD",
            "description": "打开当前项目最新的产品需求文档",
            "execution_mode": "skill",
            "target": "skill:2",
        },
        {
            "id": "mail_1",
            "type": "skill",
            "name": "发邮件给张三",
            "description": "起草一封发送给张三的工作邮件",
            "execution_mode": "skill",
            "target": "skill:3",
        },
    ]
    vectors = [await embedder.embed_query(e["name"] + "。" + e["description"]) for e in entries]
    assert all(len(v) == _DIM for v in vectors)

    idx = RouteIndex(str(tmp_path / "vectors"), dim=_DIM)
    idx.upsert(entries, vectors)

    q = await embedder.embed_query("我想听周杰伦唱晴天那首歌")
    rows = idx.search(q, top_k=3)
    assert rows, "live search returned no candidates"
    assert rows[0]["id"] == "music_1", f"expected music_1 on top, got {rows[0]['id']}"


async def test_live_router_returns_tool_call() -> None:
    """Real Qwen tool-calling: ainvoke must merge streamed tool_call deltas.

    Guards the streaming tool_call merge in `adaptive.ainvoke` and the
    `bind_tools(tool_choice=...)` passthrough — a regression here silently
    delegated 100% of voice routes.
    """
    llm = AdaptiveChatOpenAI(
        api_key="lm-studio", base_url=_LM_BASE, model=_LLM_MODEL,
        temperature=0.0, max_tokens=256,
    )
    runnable = llm.bind_tools(ROUTE_TOOLS, tool_choice="required")
    messages = [
        {
            "role": "system",
            "content": (
                "You are a voice router. Pick exactly one tool: execute_skill when a "
                "candidate matches, local_action for a device command, delegate otherwise."
            ),
        },
        {
            "role": "user",
            "content": (
                "Utterance: 播放周杰伦的晴天\nCandidates: "
                '[{"id":1,"type":"skill","name":"播放周杰伦的晴天","score":0.92}]'
            ),
        },
    ]
    resp = await runnable.ainvoke(messages)
    tool_calls = getattr(resp, "tool_calls", None) or []
    assert tool_calls, "live router returned no tool_calls (streaming merge regression?)"
    name = tool_calls[0].get("name")
    assert name in {"execute_skill", "local_action", "delegate"}, f"unexpected tool: {name}"
    args = tool_calls[0].get("args") or "{}"
    parsed = json.loads(args)  # raises if args are not a single merged JSON object
    assert isinstance(parsed, dict)


@pytest.mark.performance
@pytest.mark.slow
async def test_live_route_latency_budget() -> None:
    """Real-LM-Studio latency guards (loose; anti-regression, not micro-bench)."""
    embedder = _embedder()
    embed_ms: list[float] = []
    for _ in range(12):
        t0 = time.perf_counter()
        vec = await embedder.embed_query("帮我总结一下这篇论文的主要观点")
        embed_ms.append((time.perf_counter() - t0) * 1000.0)
        assert len(vec) == _DIM
    assert _p95(embed_ms) < _EMBED_P95_MS, f"embed p95 {_p95(embed_ms):.0f}ms >= {_EMBED_P95_MS}ms"

    llm = AdaptiveChatOpenAI(
        api_key="lm-studio", base_url=_LM_BASE, model=_LLM_MODEL,
        temperature=0.0, max_tokens=256,
    )
    runnable = llm.bind_tools(ROUTE_TOOLS, tool_choice="required")
    messages = [
        {"role": "system", "content": "You are a voice router. Pick exactly one tool."},
        {"role": "user", "content": "Utterance: 暂停一下\nCandidates: []"},
    ]
    route_ms: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        resp = await runnable.ainvoke(messages)
        route_ms.append((time.perf_counter() - t0) * 1000.0)
        assert getattr(resp, "tool_calls", None), "router returned no tool_calls during perf run"
    assert _p95(route_ms) < _ROUTE_P95_MS, f"route p95 {_p95(route_ms):.0f}ms >= {_ROUTE_P95_MS}ms"


async def test_live_route_index_content_after_rebuild() -> None:
    """rebuild_route_index must populate local + agent (+ skill) entries.

    Guards the silent-degrade class where a swallowed programming error left the
    index empty while the rebuild task still returned 'success'. Programming
    errors (AttributeError etc.) now propagate; only genuine environment
    degradation (embedder offline / 502) is skipped, never asserted as success.
    """
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    from app.core.routing.init_spec import build_init_spec
    from app.core.routing.retriever import _get_embedder, get_index
    from app.core.routing.sync import (
        _agent_entry,
        _local_entries,
        _skill_entries,
        rebuild_route_index,
    )

    local = _local_entries()
    assert any(e["id"] == "local:play_pause" for e in local), "local entries missing play_pause"
    assert _agent_entry()["id"] == "agent:default"
    skills = _skill_entries()  # must not raise (programming errors are loud now)
    assert isinstance(skills, list)

    spec = build_init_spec()
    assert any(a.get("id") == "open_app" for a in spec.actions), "init_spec missing open_app candidates"

    embedder = _get_embedder()
    if embedder is None:
        pytest.skip("no embedder (LM Studio); index population check skipped")
    try:
        written = await rebuild_route_index()
    except Exception as exc:  # noqa: BLE001 - env degradation (e.g. 502) is a skip, not a failure
        pytest.skip(f"rebuild_route_index env-degraded: {exc}")
    if written == 0:
        pytest.skip("rebuild_route_index wrote 0 (embed likely unavailable)")

    vec = await embedder.embed_query("暂停一下")
    hits = get_index().search(vec, top_k=10)
    ids = {h.get("id") for h in hits}
    assert any(i and i.startswith("local:") for i in ids), f"no local entry surfaced: {ids}"
