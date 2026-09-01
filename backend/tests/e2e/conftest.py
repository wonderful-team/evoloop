"""端到端测试公共夹具与工具（对应文档「附A 阶段0」）。

运行前提：
  1. 已启动后端服务：cd evoloop/backend && ./bin/evo start（或单独启动 API）
  2. 测试环境账号可用：preterchan / hellomylife
  3. 服务未启动时本套件将整体 skip，并提示启动命令

可通过环境变量覆盖：
  E2E_BASE_URL    服务地址（默认 http://127.0.0.1:20160）
  E2E_USERNAME    测试账号（默认 preterchan）
  E2E_PASSWORD    测试密码（默认 hellomylife）
  E2E_SKIP_LOGIN  设为 1 时跳过登录，以 guest 身份测试

运行方式：
  uv run pytest tests/e2e -v -m e2e
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import httpx
import pytest
import websockets

logger = logging.getLogger(__name__)

E2E_BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:20160")
E2E_USERNAME = os.getenv("E2E_USERNAME", "preterchan")
E2E_PASSWORD = os.getenv("E2E_PASSWORD", "hellomylife")
E2E_SKIP_LOGIN = os.getenv("E2E_SKIP_LOGIN", "0") == "1"

T = TypeVar("T")

# ---------------------------------------------------------------------------
# 基础工具函数
# ---------------------------------------------------------------------------


def gen_thread_id() -> str:
    """生成独立的测试会话 ID，避免线程间串扰。"""
    return f"e2e-{uuid.uuid4().hex[:16]}"


def gen_message_id() -> str:
    return f"msg-{uuid.uuid4().hex}"


def make_envelope(
    mtype: str, body: dict[str, Any], message_id: str | None = None
) -> dict[str, Any]:
    """构造 canonical 信封（与 app/core/schemas/canonical.py 契约一致）。"""
    return {
        "version": "2.0",
        "type": mtype,
        "message_id": message_id or gen_message_id(),
        "timestamp": int(time.time()),
        "source": None,
        "target": None,
        "body": body,
    }


async def wait_until(
    predicate: Callable[[], Awaitable[T]],
    timeout: float = 30.0,
    interval: float = 0.3,
    desc: str = "condition",
) -> T:
    """轮询等待谓词返回真值，超时抛出带描述信息的异常。"""
    deadline = time.monotonic() + timeout
    last_value: T | None = None
    while time.monotonic() < deadline:
        last_value = await predicate()
        if last_value:
            return last_value
        await asyncio.sleep(interval)
    raise TimeoutError(f"等待超时({timeout}s): {desc}, last_value={last_value!r}")


class SSEEmitter:
    """解析 /stream/chat/{thread_id} 的 SSE 文本块。"""

    def __init__(self, event: str, data: str) -> None:
        self.event = event
        self.data = data

    @property
    def json(self) -> dict[str, Any]:
        return json.loads(self.data)


_SSE_STOP = object()


async def _read_sse_stream(
    client: httpx.AsyncClient,
    url: str,
    handler: Callable[[SSEEmitter], Awaitable[Any]],
    *,
    timeout: float = 90.0,
) -> None:
    """流式读取 SSE 端点并同步调用 handler；handler 返回 _SSE_STOP 时立即结束。"""
    deadline = time.monotonic() + timeout
    async with client.stream(
        "GET", url, timeout=httpx.Timeout(timeout, read=timeout)
    ) as resp:
        resp.raise_for_status()
        event_name = ""
        data_lines: list[str] = []
        line_iter = resp.aiter_lines()
        try:
            while True:
                try:
                    line = await anext(line_iter)
                except StopAsyncIteration:
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError(f"SSE 读取超时({timeout}s)")
                if not line:
                    if event_name or data_lines:
                        control = await handler(
                            SSEEmitter(event_name, "\n".join(data_lines))
                        )
                        if control is _SSE_STOP:
                            return
                    event_name = ""
                    data_lines = []
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event: "):
                    event_name = line[len("event: ") :].strip()
                elif line.startswith("data: "):
                    data_lines.append(line[len("data: ") :].strip())
        finally:
            # 先关闭响应，再尝试排空/关闭异步生成器，避免生成器在等网络时 aclose 被挂起
            try:
                await asyncio.wait_for(resp.aclose(), timeout=1.0)
            except Exception:
                pass
            try:
                while True:
                    await asyncio.wait_for(anext(line_iter), timeout=1.0)
            except StopAsyncIteration:
                pass
            except Exception:
                pass


async def collect_sse_until(
    client: httpx.AsyncClient,
    url: str,
    pred: Callable[[SSEEmitter], bool],
    *,
    timeout: float = 90.0,
    desc: str = "目标 SSE 事件",
    on_event: Callable[[SSEEmitter], Awaitable[None]] | None = None,
) -> list[SSEEmitter]:
    """收集 SSE 事件直到谓词满足，返回全部已收到事件（含触发事件）。

    可选的 ``on_event`` 在每次收到事件后被异步调用，可用于在收集过程中
    触发副作用（例如自动取消 HITL 请求）。"""
    received: list[SSEEmitter] = []
    result: list[SSEEmitter] | None = None

    async def _handler(ev: SSEEmitter) -> Any:
        received.append(ev)
        if on_event is not None:
            await on_event(ev)
        if pred(ev):
            nonlocal result
            result = list(received)
            return _SSE_STOP
        return None

    await _read_sse_stream(client, url, _handler, timeout=timeout)
    if result is None:
        raise TimeoutError(
            f"SSE 未等到: {desc}, 已收到事件: {[e.event for e in received]}"
        )
    return result


# ---------------------------------------------------------------------------
# 认证（模块级缓存：避免每次测试重复登录）
# ---------------------------------------------------------------------------

_cached_token: str | None = None


async def _login(base_url: str) -> str | None:
    global _cached_token
    if _cached_token:
        return _cached_token
    if E2E_SKIP_LOGIN:
        return None
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
            resp = await client.post(
                "/api/v1/login/access-token",
                data={"username": E2E_USERNAME, "password": E2E_PASSWORD},
            )
            if resp.status_code == 200:
                payload = resp.json()
                _cached_token = payload.get("access_token")
                if _cached_token:
                    logger.info("登录成功: %s", E2E_USERNAME)
                    return _cached_token
        logger.warning("登录失败(status=%s): %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("登录请求异常（将以 guest 身份继续）: %s", exc)
    return None


def _guest_headers(token: str | None) -> dict[str, str]:
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {"X-Guest-Id": f"e2e-{uuid.uuid4().hex[:12]}"}


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def service_url() -> str:
    return E2E_BASE_URL


@pytest.fixture(scope="session", autouse=True)
def require_service(service_url: str) -> None:
    """阶段0-服务健康检查：服务未启动则跳过整套 e2e。"""
    try:
        resp = httpx.get(
            f"{service_url}/api/v1/system/health", timeout=3.0, follow_redirects=True
        )
        if resp.status_code == 200 and resp.json().get("status") == "ok":
            return
    except Exception as exc:
        pytest.skip(
            f"EvoLoop 服务未就绪（{service_url}，{exc}）。"
            f"请先启动服务：cd evoloop/backend && ./bin/evo start"
        )
    pytest.skip(
        f"健康检查未通过: {service_url}/api/v1/system/health "
        f"-> {resp.status_code if 'resp' in dir() else 'n/a'}。"
        f"请检查服务是否已启动：./bin/evo start"
    )


@pytest.fixture
async def access_token(service_url: str) -> str | None:
    return await _login(service_url)


@pytest.fixture
async def http_client(
    service_url: str, access_token: str | None
) -> AsyncIterator[httpx.AsyncClient]:
    headers = _guest_headers(access_token)
    async with httpx.AsyncClient(
        base_url=service_url, headers=headers, timeout=30.0
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# 共享真实依赖探测夹具（从 tests/e2e/real/conftest.py 上提到此，
# 避免非 real 目录的测试通过 import 触发 real 专属的 session 夹具）
# ---------------------------------------------------------------------------


@pytest.fixture
async def system_config(http_client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """获取系统配置列表，真实外部依赖探测用。"""
    resp = await http_client.get("/api/v1/system/config")
    resp.raise_for_status()
    return resp.json()


def _config_value(configs: list[dict[str, Any]], key: str) -> str | None:
    """从 /api/v1/system/config 返回的键值列表中提取指定键。"""
    for item in configs:
        if item.get("key") == key:
            return item.get("value")
    return None


@pytest.fixture
async def workspace_root(system_config: list[dict[str, Any]]) -> Path:
    """解析 WORKSPACE_ROOT；若后端未配置则直接失败。"""
    root = _config_value(system_config, "WORKSPACE_ROOT")
    if not root:
        pytest.fail("后端未配置 WORKSPACE_ROOT，无法执行真实工具 E2E 测试")
    return Path(root)


@pytest.fixture
async def unique_marker() -> str:
    """生成唯一标记，用于在真实命令/文件副作用中识别测试痕迹。"""
    return f"e2e-real-{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def volc_configured(system_config: list[dict[str, Any]]) -> bool:
    """探测火山引擎语音配置是否已配置。"""
    app_id = _config_value(system_config, "SEEDUPLEX_APP_ID")
    access_key = _config_value(system_config, "SEEDUPLEX_ACCESS_KEY")
    return bool(app_id and access_key)


@pytest.fixture
async def llm_configured(system_config: list[dict[str, Any]]) -> bool:
    """探测 LLM 是否已配置（至少存在 provider/model）。"""
    provider = _config_value(system_config, "LLM_PROVIDER") or _config_value(
        system_config, "LLM_PROVIDER_TYPE"
    )
    model = _config_value(system_config, "LLM_MODEL") or _config_value(
        system_config, "CUSTOM_LLM_MODEL"
    )
    return bool(provider and model)


@pytest.fixture
async def mobile_sync_enabled(system_config: list[dict[str, Any]]) -> bool:
    """探测移动端同步（EvoCloud Gateway）是否开启。"""
    value = _config_value(system_config, "MOBILE_SYNC_ENABLED")
    return value is not None and value.lower() in ("true", "1", "yes")


@pytest.fixture
def thread_id() -> str:
    return gen_thread_id()


class VoiceConn:
    """语音 WebSocket 客户端封装：自动完成握手，提供收发辅助。

    内部使用单 reader 协程持续收集消息，避免多个 wait 方法同时调用 ws.recv()
    触发 websockets 的 ConcurrencyError。
    """

    def __init__(self, ws: Any, thread_id: str) -> None:
        self.ws = ws
        self.thread_id = thread_id
        self._events: list[dict[str, Any]] = []
        self._unconsumed: list[dict[str, Any]] = []
        self._event_lock: asyncio.Lock = asyncio.Lock()
        self._event_available: asyncio.Event = asyncio.Event()
        self._reader_task: asyncio.Task | None = None
        self._closed = False
        self._audio_frames: list[tuple[float, bytes]] = []

    @classmethod
    async def connect(cls, base_url: str, thread_id: str) -> VoiceConn:
        ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws = await websockets.connect(f"{ws_url}/api/v1/voice/ws", ping_interval=None)
        conn = cls(ws, thread_id)
        conn._reader_task = asyncio.create_task(conn._reader_loop())
        # 不预握手，由各个测试自行决定是否需要消费 system.init
        return conn

    async def _reader_loop(self) -> None:
        while not self._closed:
            try:
                raw = await self.ws.recv()
            except Exception:
                break
            if isinstance(raw, bytes):
                async with self._event_lock:
                    self._audio_frames.append((time.monotonic(), raw))
                continue
            if isinstance(raw, str):
                try:
                    env = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                async with self._event_lock:
                    self._events.append(env)
                    self._unconsumed.append(env)
                self._event_available.set()

    async def _drain_until(
        self, pred: Callable[[dict[str, Any]], bool], timeout: float
    ) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            async with self._event_lock:
                for i, env in enumerate(self._unconsumed):
                    if pred(env):
                        self._unconsumed.pop(i)
                        return env
                self._event_available.clear()
            try:
                await asyncio.wait_for(
                    self._event_available.wait(),
                    timeout=min(5.0, deadline - time.monotonic()),
                )
            except asyncio.TimeoutError:
                continue
        return None

    async def send_route(self, text: str, message_id: str | None = None) -> None:
        body: dict[str, Any] = {"thread_id": self.thread_id, "text": text}
        if message_id:
            body["message_id"] = message_id
        await self.ws.send(json.dumps(make_envelope("voice.route", body)))

    async def send_type(self, mtype: str, body: dict[str, Any]) -> None:
        await self.ws.send(json.dumps(make_envelope(mtype, body)))

    async def wait_route_result(self, timeout: float = 60.0) -> dict[str, Any]:
        env = await self._drain_until(
            lambda e: e.get("type") == "voice.route_result", timeout=timeout
        )
        if env is None:
            raise TimeoutError(
                f"未收到 voice.route_result({timeout}s)，thread={self.thread_id}"
            )
        return env

    async def wait_type(self, mtype: str, timeout: float = 30.0) -> dict[str, Any]:
        env = await self._drain_until(lambda e: e.get("type") == mtype, timeout=timeout)
        if env is None:
            raise TimeoutError(f"未收到 {mtype}({timeout}s)，thread={self.thread_id}")
        return env

    async def wait_terminal_route_result(self, timeout: float = 90.0) -> dict[str, Any]:
        """等待一个终态 voice.route_result（忽略 supervisor 的 routed 安抚信封）。"""
        env = await self._drain_until(
            lambda e: (
                e.get("type") == "voice.route_result"
                and e.get("body", {}).get("status") in {"done", "failed", "cancelled"}
            ),
            timeout=timeout,
        )
        if env is None:
            raise TimeoutError(
                f"未收到终态 voice.route_result({timeout}s)，thread={self.thread_id}"
            )
        return env

    @property
    def collected_events(self) -> list[dict[str, Any]]:
        """返回当前已收集的所有 WebSocket 信封副本。"""
        return list(self._events)

    @property
    def audio_frames(self) -> list[tuple[float, bytes]]:
        """返回当前已收集的所有二进制音频帧（time.monotonic(), 原始字节）。

        后端通过 send_bytes 发送 f32le PCM 24kHz 裸字节（Rust 前端契约）。
        """
        return list(self._audio_frames)

    async def close(self) -> None:
        self._closed = True
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        try:
            await self.ws.close()
        except Exception:
            pass


@pytest.fixture
async def voice_conn(service_url: str, thread_id: str) -> AsyncIterator[VoiceConn]:
    conn = await VoiceConn.connect(service_url, thread_id)
    try:
        yield conn
    finally:
        await conn.close()


class AgentLoopResult:
    """一次真实 Agent 运行在 SSE 上的观测结果。"""

    def __init__(
        self,
        run_start: SSEEmitter | None,
        run_end: SSEEmitter | None,
        message_blocks: list[SSEEmitter],
        all_events: list[SSEEmitter],
    ) -> None:
        self.run_start = run_start
        self.run_end = run_end
        self.message_blocks = message_blocks
        self.all_events = all_events

    @property
    def run_end_status(self) -> str | None:
        if not self.run_end:
            return None
        data = self.run_end.json
        if isinstance(data, dict):
            return data.get("status") or data.get("data", {}).get("status")
        return None


async def observe_agent_run(
    client: httpx.AsyncClient,
    tid: str,
    *,
    timeout: float = 120.0,
    expect_start: bool = True,
) -> AgentLoopResult:
    """订阅 SSE 直到 run_end（或 timeout），汇总事件链。"""
    run_start: SSEEmitter | None = None
    run_end: SSEEmitter | None = None
    message_blocks: list[SSEEmitter] = []
    all_events: list[SSEEmitter] = []

    async def _handler(ev: SSEEmitter) -> Any:
        nonlocal run_start, run_end
        all_events.append(ev)
        if ev.event == "run_start":
            run_start = ev
        elif ev.event == "run_end":
            run_end = ev
            return _SSE_STOP
        elif ev.event == "message":
            message_blocks.append(ev)
        return None

    await _read_sse_stream(
        client, f"/api/v1/stream/chat/{tid}", _handler, timeout=timeout
    )
    if run_end is None:
        raise TimeoutError(f"未等到 run_end 终态事件(timeout={timeout}s)，thread={tid}")
    if expect_start and run_start is None:
        raise AssertionError(f"run_end 之前未收到 run_start 事件，thread={tid}")
    return AgentLoopResult(run_start, run_end, message_blocks, all_events)


def verify_quota_exhausted_feedback(events: list[SSEEmitter]) -> None:
    """验证配额耗尽时后端确实向前端推送了可读错误事件和消息。"""
    quota_events = [ev for ev in events if ev.event == "quota_exhausted"]
    assert quota_events, (
        f"配额耗尽时未收到 quota_exhausted SSE 事件，事件列表: {[e.event for e in events]}"
    )
    data = quota_events[0].json
    assert data.get("message"), (
        f"quota_exhausted 事件缺少可读消息: {data}"
    )
    # 至少存在一条面向用户的消息（可能是 error_system 分类）
    user_messages = [
        ev for ev in events
        if ev.event == "message"
        and isinstance(ev.json, dict)
        and ev.json.get("data", {}).get("role") in ("ai", "system")
        and ev.json.get("data", {}).get("content")
    ]
    assert user_messages, (
        f"配额耗尽时未收到面向用户的消息事件，事件列表: {[e.event for e in events]}"
    )


# ---------------------------------------------------------------------------
# 缺陷记录器：测试失败时自动生成缺陷文档
# ---------------------------------------------------------------------------

DEFECTS_DIR = Path(__file__).parent / "defects"
DEFECTS_DIR.mkdir(exist_ok=True)


def _write_defect_report(item: pytest.Item, report: pytest.TestReport) -> None:
    """根据失败的测试报告生成 Markdown 缺陷文档。"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    test_id = item.nodeid.replace("::", "-").replace("/", "-").replace(".", "_")
    filename = f"{timestamp}-{test_id}.md"
    filepath = DEFECTS_DIR / filename

    summary = f"""# E2E 缺陷报告：{item.name}

- **测试 ID**: `{item.nodeid}`
- **发现时间**: {datetime.now().isoformat()}
- **测试阶段**: {item.parent.__class__.__name__ if item.parent else "unknown"}
- **运行结果**: {report.outcome}
- **失败类型**: {report.when}

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
{report.longreprtext or report.longrepr}
```

## 环境信息

- 服务地址: {E2E_BASE_URL}
- 测试账号: {E2E_USERNAME}
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest {item.nodeid} -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
"""
    filepath.write_text(summary, encoding="utf-8")
    logger.warning("已记录缺陷报告: %s", filepath)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item,
    call: pytest.CallInfo,  # noqa: ARG001
):
    """捕获失败的真实 E2E 测试并写入缺陷文档。"""
    outcome = yield
    report = outcome.get_result()

    if report.when != "call":
        return

    if "tests/e2e" not in item.nodeid:
        return

    if report.outcome in ("failed", "error"):
        try:
            _write_defect_report(item, report)
        except Exception as exc:
            logger.error("写入缺陷报告失败: %s", exc, exc_info=True)

