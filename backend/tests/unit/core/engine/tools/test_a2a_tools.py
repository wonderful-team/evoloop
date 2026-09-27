"""a2a.py 运行时单测：设备发现 / 任务派发 / 结果回传 + task 工具转发契约。

覆盖：
- list_available_agents：只列出 online 非 mobile 设备、空列表、错误回退；
- dispatch_a2a_task：成功派发（挂起 A2A interrupt、落库 hitl_request、发布生命周期）、
  跳数超限拒绝、附件上传失败；
- complete_a2a_task：Worker 侧成功回传（关闭会话）、非 Worker 线程错误；
- task 工具 remote 分支：透传 attachments 与真实 tool_call_id（B2 修复）。
"""

import contextlib
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import app.core.engine.tools.a2a as a2a_mod
from app.core.context.manager import ContextManager, EvoContext
from app.core.evocloud.manager import evocloud_manager
from app.core.monitoring.constants import ActivityStatus


def _session_scope(rows_by_get=None, execute_rows=None):
    """返回一个 stub SQLAlchemy AsyncSession 的 asynccontextmanager 工厂。"""

    @contextlib.asynccontextmanager
    async def _scope():
        class _FakeScalars:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        class _FakeResult:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):
                return _FakeScalars(self._rows)

        class _FakeSession:
            async def get(self, model, pk):
                if isinstance(rows_by_get, dict):
                    return rows_by_get.get(pk)
                return rows_by_get

            async def execute(self, stmt):
                return _FakeResult(execute_rows or [])

        yield _FakeSession()

    return _scope


def _stack_evocloud(
    stack: ExitStack,
    send=None,
    get_devices=None,
    upload_file=None,
    caller_key: str = "dev-caller",
):
    """在 ExitStack 内打桩 EvoCloudManager 的 api/link property 底层池。"""
    api = SimpleNamespace(
        get_devices=get_devices or AsyncMock(),
        send_command_to_device=send or AsyncMock(),
        upload_file=upload_file or AsyncMock(),
    )
    stack.enter_context(patch.object(evocloud_manager, "_initialized", True))
    stack.enter_context(
        patch.object(evocloud_manager, "_api_pool", SimpleNamespace(get=lambda: api))
    )
    stack.enter_context(
        patch.object(
            evocloud_manager,
            "_link_pool",
            SimpleNamespace(get=lambda: SimpleNamespace(device_key=caller_key)),
        )
    )
    return api


# ── list_available_agents ────────────────────────────────────────────────────


async def test_list_agents_only_lists_online_non_mobile_devices():
    devices = {
        "code": 0,
        "data": {
            "list": [
                {
                    "device_key": "dev-a",
                    "device_name": "Alpha",
                    "device_type": "desktop",
                    "status": "online",
                    "description": "worker desk",
                },
                {
                    "device_key": "dev-m",
                    "device_name": "Phone",
                    "device_type": "mobile",
                    "status": "online",
                },
                {
                    "device_key": "dev-off",
                    "device_name": "Offline",
                    "device_type": "desktop",
                    "status": "offline",
                },
            ]
        },
    }
    with ExitStack() as stack:
        _stack_evocloud(stack, get_devices=AsyncMock(return_value=devices))
        out = await a2a_mod.list_available_agents()

    assert "dev-a (Alpha): worker desk" in out
    assert "dev-m" not in out
    assert "dev-off" not in out


async def test_list_agents_empty_returns_hint():
    with ExitStack() as stack:
        _stack_evocloud(stack, get_devices=AsyncMock(return_value={"code": 0, "data": {}}))
        out = await a2a_mod.list_available_agents()
    assert "当前无在线远端 Agent 设备" in out


async def test_list_agents_error_falls_back_to_message():
    with ExitStack() as stack:
        _stack_evocloud(
            stack,
            get_devices=AsyncMock(side_effect=RuntimeError("gateway down")),
        )
        out = await a2a_mod.list_available_agents()
    assert out.startswith("Error querying online agents")


# ── dispatch_a2a_task ────────────────────────────────────────────────────────


async def test_dispatch_a2a_task_success_pauses_and_persists():
    from app.core.exceptions import AgentA2AInterruptException

    ctx = EvoContext(thread_id="caller-thread", project_id=7, run_id="run-1")
    conv = SimpleNamespace(title="parent goal", root_thread_id=None, parent_thread_id=None)
    send_mock = AsyncMock()

    with ExitStack() as stack:
        stack.enter_context(ContextManager.use(ctx))
        stack.enter_context(
            patch("app.core.engine.tools.a2a.session_scope", _session_scope(rows_by_get=conv))
        )
        _stack_evocloud(stack, send=send_mock)
        pub_mock = stack.enter_context(
            patch("app.core.events.publishers.publish_a2a_lifecycle", AsyncMock())
        )
        repo_cls = stack.enter_context(
            patch("app.core.engine.message.repository.MessageRepository")
        )
        stack.enter_context(
            patch(
                "app.core.monitoring.activity.activity_monitor.set_human_request",
                AsyncMock(),
            )
        )
        stack.enter_context(
            patch(
                "app.core.environment.discovery.EnvironmentProbe.get_inferred_device_type",
                return_value="desktop",
            )
        )
        repo_cls.return_value.persist = AsyncMock()
        with pytest.raises(AgentA2AInterruptException) as einfo:
            await a2a_mod.dispatch_a2a_task("dev-target", "do the thing")

    task_id = einfo.value.request_id
    send_mock.assert_awaited_once()
    _, kwargs = send_mock.await_args
    assert kwargs["device_key"] == "dev-target"
    cmd = kwargs["cmd_data"]
    assert cmd["action"] == "a2a_task"
    assert cmd["thread_id"] == task_id
    assert cmd["project_id"] == 7
    payload = cmd["content"]
    assert payload["task_id"] == task_id
    assert payload["instruction"] == "do the thing"
    assert payload["global_goal"] == "parent goal"
    assert payload["parent_thread_id"] == "caller-thread"
    assert payload["caller_device_key"] == "dev-caller"
    assert payload["caller_role"] == "desktop"
    assert payload["hop_count"] == 1

    repo_cls.assert_called_once_with("caller-thread", project_id=7, run_id="run-1")
    persist_kwargs = repo_cls.return_value.persist.await_args.kwargs
    assert persist_kwargs["tool_name"] == "task"
    assert persist_kwargs["tool_call_id"] == f"call-{task_id}"

    pub_mock.assert_awaited_once()
    assert pub_mock.await_args.kwargs["status"] == "started"
    assert pub_mock.await_args.kwargs["target_device_key"] == "dev-target"


async def test_dispatch_a2a_task_rejects_chain_deeper_than_3():
    conv = SimpleNamespace(title="root", root_thread_id=None, parent_thread_id="h1")
    rows_by_get = {
        "caller-thread": conv,
        "h1": SimpleNamespace(parent_thread_id="h2", title="", root_thread_id=None),
        "h2": SimpleNamespace(parent_thread_id="h3", title="", root_thread_id=None),
        "h3": SimpleNamespace(parent_thread_id="h4", title="", root_thread_id=None),
        "h4": SimpleNamespace(parent_thread_id=None, title="", root_thread_id=None),
    }
    send_mock = AsyncMock()
    ctx = EvoContext(thread_id="caller-thread", project_id=7)

    with ExitStack() as stack:
        stack.enter_context(ContextManager.use(ctx))
        stack.enter_context(
            patch("app.core.engine.tools.a2a.session_scope", _session_scope(rows_by_get=rows_by_get))
        )
        _stack_evocloud(stack, send=send_mock)
        stack.enter_context(
            patch(
                "app.core.environment.discovery.EnvironmentProbe.get_inferred_device_type",
                return_value="desktop",
            )
        )
        out = await a2a_mod.dispatch_a2a_task("dev-target", "chain")

    assert "Maximum chain delegation depth" in out
    send_mock.assert_not_awaited()


async def test_dispatch_a2a_task_upload_failure_returns_error():
    ctx = EvoContext(thread_id="caller-thread", project_id=7)
    send_mock = AsyncMock()
    with ExitStack() as stack:
        stack.enter_context(ContextManager.use(ctx))
        stack.enter_context(
            patch("app.core.engine.tools.a2a.session_scope", _session_scope(rows_by_get=None))
        )
        _stack_evocloud(
            stack,
            send=send_mock,
            upload_file=AsyncMock(side_effect=RuntimeError("tos down")),
        )
        stack.enter_context(
            patch(
                "app.core.environment.discovery.EnvironmentProbe.get_inferred_device_type",
                return_value="desktop",
            )
        )
        out = await a2a_mod.dispatch_a2a_task(
            "dev-target", "task", attachments=["/tmp/a.txt"]
        )

    assert "Error uploading attachment" in out
    send_mock.assert_not_awaited()


# ── complete_a2a_task ────────────────────────────────────────────────────────


async def test_complete_a2a_task_sends_callback_and_closes_session():
    from app.core.exceptions import AgentCancelledException

    ctx = EvoContext(thread_id="worker-thread", project_id=7)
    conv = SimpleNamespace(parent_thread_id="caller-thread", caller_device_key="dev-caller")
    send_mock = AsyncMock()

    with ExitStack() as stack:
        stack.enter_context(ContextManager.use(ctx))
        stack.enter_context(
            patch("app.core.engine.tools.a2a.session_scope", _session_scope(rows_by_get=conv))
        )
        _stack_evocloud(stack, send=send_mock)
        end_mock = stack.enter_context(
            patch("app.core.monitoring.activity.activity_monitor.end_run", AsyncMock())
        )
        with pytest.raises(AgentCancelledException):
            await a2a_mod.complete_a2a_task("success", "done")

    kwargs = send_mock.await_args.kwargs
    assert kwargs["device_key"] == "dev-caller"
    cmd = kwargs["cmd_data"]
    assert cmd["action"] == "a2a_callback"
    assert cmd["thread_id"] == "caller-thread"
    content = cmd["content"]
    assert content["task_id"] == "worker-thread"
    assert content["status"] == "success"
    assert content["summary"] == "done"
    end_mock.assert_awaited_once_with(
        "worker-thread",
        status=ActivityStatus.DONE,
        final_outcome="done",
    )


async def test_complete_a2a_task_rejects_non_worker_thread():
    ctx = EvoContext(thread_id="normal-thread", project_id=7)
    conv = SimpleNamespace(parent_thread_id=None, caller_device_key=None)
    send_mock = AsyncMock()
    with ExitStack() as stack:
        stack.enter_context(ContextManager.use(ctx))
        stack.enter_context(
            patch("app.core.engine.tools.a2a.session_scope", _session_scope(rows_by_get=conv))
        )
        _stack_evocloud(stack, send=send_mock)
        out = await a2a_mod.complete_a2a_task("success", "x")

    assert "not an active A2A worker" in out
    send_mock.assert_not_awaited()


# ── task 工具 remote 分支转发契约（B2 修复）──────────────────────────────────


async def test_task_tool_forwards_attachments_and_real_tool_call_id():
    from app.core.engine.tools.react_task import task

    ctx = EvoContext(
        thread_id="caller-thread", project_id=7, current_tool_call_id="call-42"
    )
    dispatch_mock = AsyncMock(return_value="dispatched")
    with (
        ContextManager.use(ctx),
        patch("app.core.engine.tools.a2a.dispatch_a2a_task", dispatch_mock),
    ):
        out = await task(
            action="run",
            remote={"agent_id": "dev-target"},
            prompt="do it",
            attachments=["/a.txt", "/b.txt"],
            config={},
        )

    assert out == "dispatched"
    kwargs = dispatch_mock.await_args.kwargs
    assert kwargs["target_device_key"] == "dev-target"
    assert kwargs["instruction"] == "do it"
    assert kwargs["attachments"] == ["/a.txt", "/b.txt"]
    assert kwargs["tool_call_id"] == "call-42"


async def test_task_tool_remote_without_ctx_tool_call_id_passes_none():
    from app.core.engine.tools.react_task import task

    ctx = EvoContext(thread_id="caller-thread")
    dispatch_mock = AsyncMock(return_value="dispatched")
    with (
        ContextManager.use(ctx),
        patch("app.core.engine.tools.a2a.dispatch_a2a_task", dispatch_mock),
    ):
        await task(action="run", remote={"agent_id": "dev-target"}, prompt="p", config={})

    kwargs = dispatch_mock.await_args.kwargs
    assert kwargs["tool_call_id"] is None
    # a2a.py 侧 fallback 为 call-{task_id}，不会让 id 落成 None
    assert kwargs["attachments"] == []
