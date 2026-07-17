import pytest

from app.core.routing import router
from app.core.routing.schemas import RouteCandidate, RouteRequest


def _cands() -> list[RouteCandidate]:
    return [
        RouteCandidate(id="skill:42", type="skill", name="播放音乐", description="播放歌曲", score=0.9),
        RouteCandidate(id="local:open_app", type="local", name="open_app", description="打开应用", score=0.6),
        RouteCandidate(id="agent:default", type="agent", name="Agent 兜底", score=0.1),
    ]


class _Msg:
    def __init__(self, tool_calls=None, content=""):
        self.tool_calls = tool_calls or []
        self.content = content


class _Runnable:
    def __init__(self, msg):
        self._msg = msg

    async def ainvoke(self, prompt):
        return self._msg


class _FakeLLM:
    def __init__(self, msg):
        self._msg = msg
        self.bound = None

    def bind_tools(self, tools, tool_choice=None):
        self.bound = (tools, tool_choice)
        return _Runnable(self._msg)


def _patch_llm(monkeypatch, msg):
    async def _create():
        return _FakeLLM(msg)

    monkeypatch.setattr(router, "_create_route_llm", _create)
    monkeypatch.setattr(router, "_min_score", lambda: 0.55)


@pytest.mark.asyncio
async def test_route_execute_skill_valid(monkeypatch):
    msg = _Msg(tool_calls=[{"name": "execute_skill", "args": {"skill_id": 42, "params": {"song": "晴天"}}}])
    _patch_llm(monkeypatch, msg)
    d = await router.route(RouteRequest(text="播放周杰伦的晴天", thread_id="t"), _cands())
    assert d.target_type == "skill"
    assert d.target["id"] == 42
    assert d.params == {"song": "晴天"}


@pytest.mark.asyncio
async def test_route_hallucinated_skill_delegates(monkeypatch):
    msg = _Msg(tool_calls=[{"name": "execute_skill", "args": {"skill_id": 999}}])
    _patch_llm(monkeypatch, msg)
    d = await router.route(RouteRequest(text="播放", thread_id="t"), _cands())
    assert d.target_type == "agent"
    assert d.status == "routed"


@pytest.mark.asyncio
async def test_route_local_action_unknown_delegates(monkeypatch):
    msg = _Msg(tool_calls=[{"name": "local_action", "args": {"action": "fly"}}])
    _patch_llm(monkeypatch, msg)
    d = await router.route(RouteRequest(text="飞", thread_id="t"), _cands())
    assert d.target_type == "agent"


@pytest.mark.asyncio
async def test_route_local_action_valid(monkeypatch):
    msg = _Msg(tool_calls=[{"name": "local_action", "args": {"action": "open_app", "params": {"app": "微信"}}}])
    _patch_llm(monkeypatch, msg)
    d = await router.route(RouteRequest(text="打开微信", thread_id="t"), _cands())
    assert d.target_type == "local"
    assert d.target["id"] == "open_app"
    assert d.params == {"app": "微信"}


@pytest.mark.asyncio
async def test_route_delegate_tool(monkeypatch):
    msg = _Msg(tool_calls=[{"name": "delegate", "args": {"task": "找最新 PRD"}}])
    _patch_llm(monkeypatch, msg)
    d = await router.route(RouteRequest(text="找最新 PRD", thread_id="t"), _cands())
    assert d.target_type == "agent"
    assert d.params["task"] == "找最新 PRD"


@pytest.mark.asyncio
async def test_route_early_delegate_low_score(monkeypatch):
    async def _boom():
        raise AssertionError("LLM must not be called on early delegate")

    monkeypatch.setattr(router, "_create_route_llm", _boom)
    monkeypatch.setattr(router, "_min_score", lambda: 0.55)
    low = [RouteCandidate(id="skill:1", type="skill", name="x", score=0.1)]
    d = await router.route(RouteRequest(text="xxx", thread_id="t"), low)
    assert d.target_type == "agent"


@pytest.mark.asyncio
async def test_route_llm_exception_delegates(monkeypatch):
    async def _boom():
        raise RuntimeError("lmstudio down")

    monkeypatch.setattr(router, "_create_route_llm", _boom)
    monkeypatch.setattr(router, "_min_score", lambda: 0.0)
    d = await router.route(RouteRequest(text="xxx", thread_id="t"), _cands())
    assert d.target_type == "agent"


@pytest.mark.asyncio
async def test_route_hermes_fallback(monkeypatch):
    content = '<tool_call>{"name": "local_action", "arguments": {"action": "open_app", "params": {"app": "微信"}}}</tool_call>'
    msg = _Msg(tool_calls=[], content=content)
    _patch_llm(monkeypatch, msg)
    d = await router.route(RouteRequest(text="打开微信", thread_id="t"), _cands())
    assert d.target_type == "local"
    assert d.target["id"] == "open_app"


@pytest.mark.asyncio
async def test_route_httpx_error_delegates(monkeypatch):
    """Network/HTTP SDK errors must degrade to delegate, never leak (§8.5)."""
    import httpx

    async def _boom():
        raise httpx.ConnectError("lmstudio unreachable")

    monkeypatch.setattr(router, "_create_route_llm", _boom)
    monkeypatch.setattr(router, "_min_score", lambda: 0.0)
    d = await router.route(RouteRequest(text="xxx", thread_id="t"), _cands())
    assert d.target_type == "agent"
    assert d.status == "routed"


def test_min_score_default_calibrated_for_bge(monkeypatch):
    """bge-base-zh on this corpus: genuine short-phrase matches score
    ~0.24-0.31, irrelevant ~-0.18. The gate must let genuine matches reach
    the LLM (which makes the final call) — the old 0.55 delegated everything."""
    monkeypatch.setattr(router, "_cfg", lambda key, default=None: default)
    assert router._min_score() == 0.15
