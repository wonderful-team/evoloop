"""A2ACommandHandler 单测（event/handlers/a2a.py）。

覆盖：
- B3: _handle_a2a_callback 无活会话回落的 project_id 透传（不再回退 DEFAULT_PROJECT_ID）；
- 回调写回 tool 消息 / close_hitl_message / 生命周期事件 / 会话注入分支；
- B4: _handle_a2a_task 附件下载 + MD5 校验（文件 IO 走 asyncio.to_thread，无同步 open）；
- 错误回调（下载失败 / MD5 不一致 / 跳数超限 / agent 派发失败）。
"""

import asyncio
import contextlib
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.core.context.manager import EvoContext
from app.core.engine.agent import BackgroundAgentInputs
from app.core.engine.dispatch import DispatchStatus
from app.core.engine.event.handlers.a2a import (
    A2AAttachmentError,
    A2ACommandHandler,
    download_and_verify_attachment,
)
from app.core.engine.message.constants import MessageStatus
from app.core.engine.session.manager import session_manager
from app.core.evocloud.manager import evocloud_manager
from app.core.evocloud.schemas import (
    AgentTask,
    AgentTaskResult,
    RemoteCommand,
    TaskAttachment,
)

# handler 模块内 asyncio 引用替换：create_task 真调度、to_thread 真执行，
# 避免 create_task 无法断言被调用的 coroutine。
FAKE_ASYNCIO = SimpleNamespace(
    create_task=lambda coro: asyncio.ensure_future(coro),
    to_thread=asyncio.to_thread,
)


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


def _scope_with(rows=None, conv=None):
    @contextlib.asynccontextmanager
    async def _scope():
        class _FakeSession:
            async def get(self, model, pk):
                return conv() if callable(conv) else conv

            async def execute(self, stmt):
                return _FakeResult(rows or [])

            def add(self, obj):
                pass

        yield _FakeSession()

    return _scope


def _stream_cm(data):
    @contextlib.asynccontextmanager
    async def _stream(method, url, **kwargs):  # noqa: ARG001
        class _Resp:
            def raise_for_status(self):
                return None

            async def aiter_bytes(self):
                yield data

        yield _Resp()

    return _stream


def _stream_cm_raising(exc):
    @contextlib.asynccontextmanager
    async def _stream(method, url, **kwargs):  # noqa: ARG001
        class _Resp:
            def raise_for_status(self):
                raise exc

            async def aiter_bytes(self):
                yield b""

        yield _Resp()

    return _stream


class _ClientCM:
    """Stub for ``async with httpx.AsyncClient()`` returning a fake client."""

    def __init__(self, stream_fn):
        self._stream_fn = stream_fn

    async def __aenter__(self):
        return SimpleNamespace(stream=self._stream_fn)

    async def __aexit__(self, *exc):
        return False


@contextlib.contextmanager
def _patch_error_callback(send=AsyncMock()):
    """打桩 evocloud api（EvoCloudManager.api 是只读 property，改底层池）。"""
    fake_api = SimpleNamespace(send_command_to_device=send)
    with (
        patch.object(evocloud_manager, "_initialized", True),
        patch.object(
            evocloud_manager,
            "_api_pool",
            SimpleNamespace(get=lambda: fake_api),
        ),
        patch.object(
            evocloud_manager,
            "_link_pool",
            SimpleNamespace(get=lambda: SimpleNamespace(device_key="dev-caller")),
        ),
    ):
        yield


def _task_command(task: AgentTask) -> RemoteCommand:
    return RemoteCommand(
        action="a2a_task",
        content=task.model_dump(),
        thread_id=task.task_id,
        project_id=7,
        command_id=99,
    )


# ── _handle_a2a_callback：B3 回落 project_id 透传 ─────────────────────────────


async def test_callback_resume_fallback_passes_caller_project_id():
    handler = A2ACommandHandler()
    result = AgentTaskResult(task_id="t-1", status="success", summary="done")
    cmd = RemoteCommand(
        action="a2a_callback", content=result.model_dump(), thread_id="caller-thread"
    )
    tool_msg = SimpleNamespace(
        tool_calls=[
            {
                "id": "call-9",
                "name": "task",
                "args": {"remote": {"agent_id": "dev-a"}, "prompt": "p"},
            }
        ]
    )
    fake_repo = MagicMock()
    fake_repo.update_content_by_tool_call_id = AsyncMock()
    fake_repo.update_ai_tool_message_content = AsyncMock()
    run_mock = AsyncMock()

    with (
        patch("app.core.engine.event.handlers.a2a.asyncio", FAKE_ASYNCIO),
        patch("app.core.engine.event.handlers.a2a.session_scope", _scope_with(rows=[tool_msg])),
        patch("app.infrastructure.database.session_scope", _scope_with(rows=[tool_msg])),
        patch(
            "app.core.context.manager.ContextManager.load",
            AsyncMock(
                return_value=EvoContext(
                    thread_id="caller-thread", project_id=42, active_model="m"
                )
            ),
        ),
        patch.object(session_manager, "get", return_value=None),
        patch("app.core.monitoring.activity.activity_monitor.clear_human_request", AsyncMock()),
        patch("app.core.engine.message.repository.MessageRepository", return_value=fake_repo),
        patch("app.core.hitl.orchestrator.close_hitl_message", AsyncMock()) as close_mock,
        patch("app.core.events.publishers.publish_a2a_lifecycle", AsyncMock()) as pub_mock,
        patch("app.core.engine.event.handlers.a2a.run_agent_background", run_mock),
    ):
        await handler._handle_a2a_callback(cmd)
        await asyncio.sleep(0)

    args = run_mock.await_args.args
    assert args[0] == "caller-thread"
    inputs = args[1]
    assert isinstance(inputs, BackgroundAgentInputs)
    assert inputs.project_id == 42
    assert inputs.model == "m"

    expected_json = json.dumps(result.model_dump(), ensure_ascii=False)
    assert inputs.hitl_resume_response == expected_json
    fake_repo.update_content_by_tool_call_id.assert_awaited_once_with(
        "call-9", expected_json
    )
    fake_repo.update_ai_tool_message_content.assert_awaited_once_with(
        "call-9", expected_json
    )
    close_mock.assert_awaited_once_with("caller-thread", "call-9", MessageStatus.COMPLETED)
    pub_mock.assert_awaited_once()
    assert pub_mock.await_args.kwargs["status"] == "completed"


async def test_callback_resume_fallback_without_context_keeps_default_project():
    handler = A2ACommandHandler()
    result = AgentTaskResult(task_id="t-2", status="success", summary="ok")
    cmd = RemoteCommand(
        action="a2a_callback", content=result.model_dump(), thread_id="caller-thread"
    )
    tool_msg = SimpleNamespace(
        tool_calls=[{"id": "call-1", "name": "task", "args": {"remote": {}}}]
    )
    fake_repo = MagicMock()
    fake_repo.update_content_by_tool_call_id = AsyncMock()
    fake_repo.update_ai_tool_message_content = AsyncMock()
    run_mock = AsyncMock()

    with (
        patch("app.core.engine.event.handlers.a2a.asyncio", FAKE_ASYNCIO),
        patch("app.core.engine.event.handlers.a2a.session_scope", _scope_with(rows=[tool_msg])),
        patch("app.infrastructure.database.session_scope", _scope_with(rows=[tool_msg])),
        patch("app.core.context.manager.ContextManager.load", AsyncMock(return_value=None)),
        patch.object(session_manager, "get", return_value=None),
        patch("app.core.monitoring.activity.activity_monitor.clear_human_request", AsyncMock()),
        patch("app.core.engine.message.repository.MessageRepository", return_value=fake_repo),
        patch("app.core.hitl.orchestrator.close_hitl_message", AsyncMock()),
        patch("app.core.events.publishers.publish_a2a_lifecycle", AsyncMock()),
        patch("app.core.engine.event.handlers.a2a.run_agent_background", run_mock),
    ):
        await handler._handle_a2a_callback(cmd)
        await asyncio.sleep(0)

    inputs = run_mock.await_args.args[1]
    # 无缓存上下文时保持 None（runner 端再回退 DEFAULT_PROJECT_ID），不伪造项目归属
    assert inputs.project_id is None
    assert inputs.model is None


async def test_callback_resume_live_session_injects_without_background_run():
    handler = A2ACommandHandler()
    result = AgentTaskResult(task_id="t-3", status="failed", error="nope")
    cmd = RemoteCommand(
        action="a2a_callback", content=result.model_dump(), thread_id="caller-thread"
    )
    tool_msg = SimpleNamespace(
        tool_calls=[
            {"id": "call-5", "name": "task", "args": {"remote": {"agent_id": "x"}}}
        ]
    )
    fake_repo = MagicMock()
    fake_repo.update_content_by_tool_call_id = AsyncMock()
    fake_repo.update_ai_tool_message_content = AsyncMock()
    fake_session = SimpleNamespace(lifecycle="running", inject_resume=MagicMock())
    run_mock = AsyncMock()

    with (
        patch("app.core.engine.event.handlers.a2a.asyncio", FAKE_ASYNCIO),
        patch("app.core.engine.event.handlers.a2a.session_scope", _scope_with(rows=[tool_msg])),
        patch("app.infrastructure.database.session_scope", _scope_with(rows=[tool_msg])),
        patch(
            "app.core.context.manager.ContextManager.load",
            AsyncMock(return_value=EvoContext(thread_id="caller-thread", project_id=42)),
        ),
        patch.object(session_manager, "get", return_value=fake_session),
        patch("app.core.monitoring.activity.activity_monitor.clear_human_request", AsyncMock()),
        patch("app.core.engine.message.repository.MessageRepository", return_value=fake_repo),
        patch("app.core.hitl.orchestrator.close_hitl_message", AsyncMock()),
        patch("app.core.events.publishers.publish_a2a_lifecycle", AsyncMock()),
        patch("app.core.engine.event.handlers.a2a.run_agent_background", run_mock),
    ):
        await handler._handle_a2a_callback(cmd)

    expected_json = json.dumps(result.model_dump(), ensure_ascii=False)
    fake_session.inject_resume.assert_called_once_with(expected_json, kind="a2a_result")
    run_mock.assert_not_awaited()


async def test_callback_without_matching_tool_call_skips_repo_write():
    handler = A2ACommandHandler()
    result = AgentTaskResult(task_id="t-4", status="success", summary="ok")
    cmd = RemoteCommand(
        action="a2a_callback", content=result.model_dump(), thread_id="caller-thread"
    )
    repo_cls = MagicMock()
    run_mock = AsyncMock()

    with (
        patch("app.core.engine.event.handlers.a2a.asyncio", FAKE_ASYNCIO),
        patch("app.core.engine.event.handlers.a2a.session_scope", _scope_with(rows=[SimpleNamespace(tool_calls=None)])),
        patch("app.infrastructure.database.session_scope", _scope_with(rows=[SimpleNamespace(tool_calls=None)])),
        patch(
            "app.core.context.manager.ContextManager.load",
            AsyncMock(return_value=EvoContext(thread_id="caller-thread", project_id=42)),
        ),
        patch.object(session_manager, "get", return_value=None),
        patch("app.core.monitoring.activity.activity_monitor.clear_human_request", AsyncMock()),
        patch("app.core.engine.message.repository.MessageRepository", repo_cls),
        patch("app.core.events.publishers.publish_a2a_lifecycle", AsyncMock()),
        patch("app.core.engine.event.handlers.a2a.run_agent_background", run_mock),
    ):
        await handler._handle_a2a_callback(cmd)
        await asyncio.sleep(0)

    repo_cls.assert_not_called()
    assert run_mock.await_args.args[0] == "caller-thread"


# ── download_and_verify_attachment（B4 底层）──────────────────────────────────


async def test_download_and_verify_attachment_success(tmp_path):
    payload = b"hello world"
    att = TaskAttachment(
        filename="a.txt",
        download_url="http://cdn/a",
        file_size=len(payload),
        md5=hashlib.md5(payload).hexdigest(),
    )
    client = SimpleNamespace(stream=_stream_cm(payload))

    dest = await download_and_verify_attachment(client, att, str(tmp_path))

    assert Path(dest).read_bytes() == payload
    assert Path(dest).parent == tmp_path


async def test_download_and_verify_attachment_md5_mismatch(tmp_path):
    payload = b"hello world"
    att = TaskAttachment(
        filename="a.txt",
        download_url="http://cdn/a",
        file_size=len(payload),
        md5="deadbeef",
    )
    client = SimpleNamespace(stream=_stream_cm(payload))

    with pytest.raises(A2AAttachmentError, match="MD5 mismatch"):
        await download_and_verify_attachment(client, att, str(tmp_path))


async def test_download_and_verify_attachment_network_failure(tmp_path):
    att = TaskAttachment(
        filename="a.txt",
        download_url="http://cdn/a",
        file_size=0,
        md5="x",
    )
    client = SimpleNamespace(
        stream=_stream_cm_raising(RuntimeError("connection reset"))
    )

    with pytest.raises(A2AAttachmentError, match="Failed to download"):
        await download_and_verify_attachment(client, att, str(tmp_path))


# ── _handle_a2a_task：B4 附件下载 + 派发 ─────────────────────────────────────


async def test_handle_a2a_task_downloads_attachments_and_dispatches(tmp_path):
    payload = b"content-123"
    att = TaskAttachment(
        filename="f.txt",
        download_url="http://cdn/f",
        file_size=len(payload),
        md5=hashlib.md5(payload).hexdigest(),
    )
    task = AgentTask(
        task_id="t1",
        instruction="do it",
        caller_device_key="dev-caller",
        root_thread_id="root",
        parent_thread_id="parent",
        global_goal="g",
        attachments=[att],
    )
    cmd = _task_command(task)
    run_mock = AsyncMock()

    with (
        patch("app.core.engine.event.handlers.a2a.asyncio", FAKE_ASYNCIO),
        patch("app.core.engine.event.handlers.a2a.session_scope", _scope_with(conv=None)),
        patch("app.infrastructure.database.session_scope", _scope_with(conv=None)),
        patch.object(settings, "EVOLOOP_APP_DATA_DIR", str(tmp_path)),
        patch("app.core.engine.event.handlers.a2a.httpx.AsyncClient") as hcls,
        patch("app.core.engine.message.repository.MessageRepository") as repo_cls,
        patch(
            "app.core.engine.event.handlers.a2a.render_template", return_value="SYSTEM"
        ),
        patch(
            "app.core.engine.event.handlers.a2a.dispatch_agent_run",
            AsyncMock(
                return_value=SimpleNamespace(
                    status=DispatchStatus.QUEUED, inputs=object()
                )
            ),
        ) as disp_mock,
        patch("app.core.engine.event.handlers.a2a.run_agent_background", run_mock),
    ):
        repo_cls.return_value.persist = AsyncMock()
        hcls.return_value = _ClientCM(_stream_cm(payload))
        await A2ACommandHandler()._handle_a2a_task(cmd)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    dest = tmp_path / "attachments" / "t1" / "f.txt"
    assert dest.read_bytes() == payload

    disp_mock.assert_awaited_once()
    _, kw = disp_mock.await_args
    assert kw["thread_id"] == "t1"
    assert kw["project_id"] == 7
    assert kw["message_content"] == "do it"
    assert kw["metadata"]["task_type"] == "a2a_task"

    run_mock.assert_awaited_once()
    assert run_mock.await_args.args[0] == "t1"

    persist_kwargs = repo_cls.return_value.persist.await_args.kwargs
    assert persist_kwargs["role"] == "system"


async def test_handle_a2a_task_md5_mismatch_sends_error_and_returns(tmp_path):
    payload = b"content-123"
    att = TaskAttachment(
        filename="f.txt",
        download_url="http://cdn/f",
        file_size=len(payload),
        md5="deadbeef",
    )
    task = AgentTask(
        task_id="t2",
        instruction="do it",
        caller_device_key="dev-caller",
        root_thread_id="root",
        parent_thread_id="parent",
        global_goal="g",
        attachments=[att],
    )
    cmd = _task_command(task)
    send_mock = AsyncMock()

    with (
        patch("app.core.engine.event.handlers.a2a.asyncio", FAKE_ASYNCIO),
        patch("app.core.engine.event.handlers.a2a.session_scope", _scope_with(conv=None)),
        patch("app.infrastructure.database.session_scope", _scope_with(conv=None)),
        patch.object(settings, "EVOLOOP_APP_DATA_DIR", str(tmp_path)),
        patch("app.core.engine.event.handlers.a2a.httpx.AsyncClient") as hcls,
        patch("app.core.engine.message.repository.MessageRepository") as repo_cls,
        patch("app.core.engine.event.handlers.a2a.render_template", return_value="SYSTEM"),
        patch(
            "app.core.engine.event.handlers.a2a.dispatch_agent_run",
            AsyncMock(return_value=SimpleNamespace(status=DispatchStatus.QUEUED)),
        ) as disp_mock,
        _patch_error_callback(send=send_mock),
    ):
        repo_cls.return_value.persist = AsyncMock()
        hcls.return_value = _ClientCM(_stream_cm(payload))
        await A2ACommandHandler()._handle_a2a_task(cmd)

    disp_mock.assert_not_awaited()
    send_mock.assert_awaited_once()
    _, kw = send_mock.await_args
    assert kw["device_key"] == "dev-caller"
    assert kw["cmd_data"]["action"] == "a2a_callback"
    assert kw["cmd_data"]["thread_id"] == "parent"
    error = kw["cmd_data"]["content"]["error"]
    assert "MD5 mismatch" in error


async def test_handle_a2a_task_hops_exceeded_sends_error(tmp_path):
    task = AgentTask(
        task_id="t3",
        instruction="do it",
        caller_device_key="dev-caller",
        root_thread_id="root",
        parent_thread_id="parent",
        global_goal="g",
        hop_count=4,
        max_hops=3,
    )
    cmd = _task_command(task)
    send_mock = AsyncMock()

    with (
        patch("app.core.engine.event.handlers.a2a.asyncio", FAKE_ASYNCIO),
        patch("app.core.engine.event.handlers.a2a.session_scope", _scope_with(conv=None)),
        patch("app.infrastructure.database.session_scope", _scope_with(conv=None)),
        patch.object(settings, "EVOLOOP_APP_DATA_DIR", str(tmp_path)),
        patch(
            "app.core.engine.event.handlers.a2a.dispatch_agent_run",
            AsyncMock(return_value=SimpleNamespace(status=DispatchStatus.QUEUED)),
        ) as disp_mock,
        _patch_error_callback(send=send_mock),
    ):
        await A2ACommandHandler()._handle_a2a_task(cmd)

    disp_mock.assert_not_awaited()
    send_mock.assert_awaited_once()
    error = send_mock.await_args.kwargs["cmd_data"]["content"]["error"]
    assert "Maximum chain delegation depth" in error


async def test_handle_a2a_task_dispatch_failure_sends_error(tmp_path):
    task = AgentTask(
        task_id="t4",
        instruction="do it",
        caller_device_key="dev-caller",
        root_thread_id="root",
        parent_thread_id="parent",
        global_goal="g",
    )
    cmd = _task_command(task)
    send_mock = AsyncMock()
    run_mock = AsyncMock()

    with (
        patch("app.core.engine.event.handlers.a2a.asyncio", FAKE_ASYNCIO),
        patch("app.core.engine.event.handlers.a2a.session_scope", _scope_with(conv=None)),
        patch("app.infrastructure.database.session_scope", _scope_with(conv=None)),
        patch.object(settings, "EVOLOOP_APP_DATA_DIR", str(tmp_path)),
        patch("app.core.engine.message.repository.MessageRepository") as repo_cls,
        patch("app.core.engine.event.handlers.a2a.render_template", return_value="SYSTEM"),
        patch(
            "app.core.engine.event.handlers.a2a.dispatch_agent_run",
            AsyncMock(
                return_value=SimpleNamespace(
                    status=DispatchStatus.FAILED, error="boom"
                )
            ),
        ) as disp_mock,
        patch("app.core.engine.event.handlers.a2a.run_agent_background", run_mock),
        _patch_error_callback(send=send_mock),
    ):
        repo_cls.return_value.persist = AsyncMock()
        await A2ACommandHandler()._handle_a2a_task(cmd)

    disp_mock.assert_awaited_once()
    run_mock.assert_not_awaited()
    send_mock.assert_awaited_once()
    error = send_mock.await_args.kwargs["cmd_data"]["content"]["error"]
    assert "boom" in error
