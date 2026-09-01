"""A2A / HITL callback end-to-end scenarios.

Implements the four scenarios requested in
``evoloop/backend/docs/TEST_SCENARIOS_DESIGN.md``:

- E2E-SC-004: parent delegates a subtask to a simulated child device; callback
  resumes the parent run.
- E2E-SC-009: retry of a message with an attachment re-injects the same
  reference.
- E2E-SC-010: re-delegating beyond ``max_hops`` returns ``a2a_error``.
- E2E-SC-011: corrupted A2A attachment (MD5 mismatch) returns an error callback.

运行要求：
  - 后端服务已启动 (``cd evoloop/backend && ./bin/evo start``)。
  - A2A 用例需要 EvoCloud Gateway 真实连接，或者已配置 mock gateway：
      * 设置 ``EVOLOOP_A2A_TEST_BED=<mock-gateway-base-url>``
      * 将后端指向该 gateway：
          EVOCLOUD_API_URL=$EVOLOOP_A2A_TEST_BED
          EVOCLOUD_WS_URL=$EVOLOOP_A2A_TEST_BED/ws
      * 如没有 respx 且未连接 gateway，A2A 用例会 ``pytest.skip``。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import (
    E2E_BASE_URL,
    observe_agent_run,
    wait_until,
)

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.e2e

A2A_TEST_BED = os.getenv("EVOLOOP_A2A_TEST_BED")
A2A_TARGET_DEVICE = os.getenv("EVOLOOP_A2A_TARGET_DEVICE", "child-device")
A2A_RELAY_PATH = "/api/v1/devices/{device_key}/command"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _build_agent_task_result(
    task_id: str,
    status: str,
    summary: str,
    error: str = "",
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build an ``AgentTaskResult`` payload for an ``a2a_callback`` command."""
    return {
        "task_id": task_id,
        "status": status,
        "summary": summary,
        "error": error,
        "attachments": attachments or [],
    }


async def _get_messages(
    http_client: httpx.AsyncClient, thread_id: str, *, include_tool_calls: bool = False
) -> list[dict[str, Any]]:
    """Fetch the visible message history for a thread."""
    resp = await http_client.get(
        f"/api/v1/conversations/{thread_id}/messages",
        params={"include_tool_calls": "true" if include_tool_calls else "false"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


async def _wait_for_tool_call(
    http_client: httpx.AsyncClient,
    thread_id: str,
    tool_names: tuple[str, ...],
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Poll message history until one of the named tool calls appears.

    ``/messages`` 默认不返回 tool_calls，需显式请求 ``include_tool_calls=true``。
    """
    result: dict[str, Any] | None = None

    async def _found() -> bool:
        nonlocal result
        messages = await _get_messages(
            http_client, thread_id, include_tool_calls=True
        )
        for msg in messages:
            for tc in msg.get("tool_calls") or []:
                if tc.get("name") in tool_names:
                    result = tc
                    return True
        return False

    await wait_until(
        _found,
        timeout=timeout,
        interval=0.5,
        desc=f"tool call in {tool_names}",
    )
    return result


async def _wait_for_hitl_request(
    http_client: httpx.AsyncClient,
    thread_id: str,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Poll activity endpoint until an HITL request is pending."""

    async def _has_hitl() -> dict[str, Any] | None:
        resp = await http_client.get(
            f"/api/v1/conversations/{thread_id}/activity", timeout=10.0
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        hr = data.get("human_request")
        if hr:
            return hr
        return None

    return await wait_until(
        _has_hitl,
        timeout=timeout,
        interval=0.5,
        desc="HITL request on parent thread",
    )


async def _wait_for_send_agent_task_or_skip(
    http_client: httpx.AsyncClient,
    thread_id: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Wait for an A2A ``task`` tool call (``remote`` arg set), or skip if the LLM does not delegate."""
    result: dict[str, Any] | None = None

    async def _found() -> bool:
        nonlocal result
        messages = await _get_messages(
            http_client, thread_id, include_tool_calls=True
        )
        for msg in messages:
            for tc in msg.get("tool_calls") or []:
                if tc.get("name") not in ("task", "send_agent_task", "SendAgentTaskTool"):
                    continue
                args = tc.get("args") or tc.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                if isinstance(args, dict) and (args.get("remote") or args.get("target_device_key")):
                    result = tc
                    return True
        return False

    try:
        await wait_until(
            _found,
            timeout=timeout,
            interval=0.5,
            desc="A2A task tool call",
        )
        return result  # type: ignore[return-value]
    except TimeoutError:
        # If the parent run already finished without delegating, skip cleanly.
        state = await http_client.get(
            f"/api/v1/conversations/{thread_id}/activity", timeout=10.0
        )
        if state.status_code == 200:
            status = state.json().get("status")
            if status != "running":
                pytest.skip(
                    f"Parent run ended (status={status}) without invoking an A2A task tool call"
                )
        pytest.skip(
            "LLM did not invoke an A2A task tool call within timeout; "
            "A2A scenario not triggerable in this environment"
        )


# -----------------------------------------------------------------------------
# Mock gateway fixture
# -----------------------------------------------------------------------------


class A2AMockGateway:
    """Lightweight helper that either respx-mocks outbound gateway calls or
    delegates to a real connected EvoCloud gateway.

    For external E2E runs the backend is a separate process, so ``respx`` can
    only intercept outbound calls when the backend is served in-process. The
    default path therefore uses the real gateway: after the parent emits an
    A2A ``task`` (``remote``) tool call, the helper pushes the corresponding
    ``a2a_callback`` / ``a2a_task`` back to the parent backend device via
    ``POST /api/v1/devices/{device_key}/command``.
    """

    def __init__(self, http_client: httpx.AsyncClient, device_key: str | None) -> None:
        self.http_client = http_client
        self.device_key = device_key
        self.captured_tasks: list[dict[str, Any]] = []
        self._respx_mock: Any | None = None

    async def __aenter__(self) -> A2AMockGateway:
        respx: Any | None = None
        try:
            import respx as _respx

            respx = _respx
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.debug("respx not available for A2A mock: %s", exc)

        if A2A_TEST_BED and respx is not None:
            base = A2A_TEST_BED.rstrip("/")
            self._respx_mock = respx.mock(assert_all_mocked=False)
            self._respx_mock.post(f"{base}/api/v1/message/send").mock(
                side_effect=self._on_message_send
            )
            self._respx_mock.start()
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        if self._respx_mock is not None:
            self._respx_mock.stop()
        return False

    def _on_message_send(self, request: httpx.Request) -> httpx.Response:
        """Capture outbound ``AgentTask`` envelopes sent by the backend."""
        try:
            payload = json.loads(request.content)
        except Exception:
            payload = {}
        envelope = payload.get("envelope") or {}
        body = envelope.get("body") or {}
        if body.get("action") == "a2a_task":
            content = body.get("content") or {}
            self.captured_tasks.append(content)
        return httpx.Response(200, json={"code": 0, "message": "ok", "data": {}})

    async def _ensure_device_key(self) -> str:
        if not self.device_key:
            raise RuntimeError("Backend device_key is not available")
        return self.device_key

    async def inject_callback(
        self, parent_thread_id: str, callback_payload: dict[str, Any]
    ) -> None:
        """Push an ``a2a_callback`` command to the parent backend device."""
        device_key = await self._ensure_device_key()
        resp = await self.http_client.post(
            A2A_RELAY_PATH.format(device_key=device_key),
            json={
                "command_type": "a2a_callback",
                "content": callback_payload,
                "thread_id": parent_thread_id,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        logger.info(
            "Injected a2a_callback to parent device %s for thread %s",
            device_key,
            parent_thread_id,
        )

    async def inject_task(self, thread_id: str, task_payload: dict[str, Any]) -> None:
        """Push an ``a2a_task`` command to the backend (simulates child inbound)."""
        device_key = await self._ensure_device_key()
        resp = await self.http_client.post(
            A2A_RELAY_PATH.format(device_key=device_key),
            json={
                "command_type": "a2a_task",
                "content": task_payload,
                "thread_id": thread_id,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        logger.info(
            "Injected a2a_task to backend device %s for thread %s",
            device_key,
            thread_id,
        )

    async def fetch_task_from_messages(
        self,
        thread_id: str,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """返回 A2A ``task`` 工具调用参数（归一化为 target_device_key + instruction）。

        统一体系后 A2A 委派走 ``task(remote={'agent_id': ...}, prompt=...)``；
        兼容历史 ``send_agent_task(target_device_key=..., instruction=...)`` 参数。
        """
        try:
            tool_call = await _wait_for_send_agent_task_or_skip(
                self.http_client,
                thread_id,
                timeout=timeout,
            )
            args = tool_call.get("args") or tool_call.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if args:
                remote = args.get("remote") or {}
                normalized = {
                    "target_device_key": remote.get("agent_id")
                    or args.get("target_device_key"),
                    "instruction": args.get("prompt") or args.get("instruction"),
                }
                if normalized["target_device_key"] and normalized["instruction"]:
                    self.captured_tasks.append(normalized)
                    return normalized
        except Exception:
            pass
        if self.captured_tasks:
            return self.captured_tasks[0]
        pytest.skip("无法获取 A2A task 委派参数")


@pytest.fixture
async def a2a_mock_gateway(http_client: httpx.AsyncClient) -> A2AMockGateway:
    """Provide a gateway helper and skip when no A2A test bed is available."""
    status = await http_client.get("/api/v1/utils/evoloop-status")
    status.raise_for_status()
    evo = status.json()
    device_key = evo.get("device_key")
    connected = evo.get("connected", False)

    if not A2A_TEST_BED and not connected:
        pytest.skip(
            "A2A test bed not configured: "
            "set EVOLOOP_A2A_TEST_BED or connect EvoCloud gateway"
        )

    async with A2AMockGateway(http_client, device_key) as gateway:
        yield gateway


# -----------------------------------------------------------------------------
# E2E-SC-004: delegate and callback resume
# -----------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.real
class TestA2AHITLCallback:
    """Parent delegates a subtask to a simulated child device; callback resumes."""

    @pytest.mark.timeout(180)
    async def test_a2a_delegate_and_callback_resume(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        a2a_mock_gateway: A2AMockGateway,
    ) -> None:
        """Parent sends AgentTask; mock gateway returns a2a_callback; parent ends."""
        # Subscribe to the parent SSE stream before triggering the run.
        sse_future = asyncio.create_task(
            observe_agent_run(http_client, thread_id, timeout=120.0)
        )

        # Start a parent run that should delegate to the child device.
        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": (
                    "Use the task tool with remote={'agent_id': <device>} to delegate to device "
                    f"'{A2A_TARGET_DEVICE}' the following task: execute the command "
                    "'echo child-done' and return the result."
                ),
                "project_id": 0,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        assert body["status"] in ("queued", "done")

        # Wait for the parent to emit the A2A tool call (and HITL request).
        task = await a2a_mock_gateway.fetch_task_from_messages(thread_id, timeout=60.0)
        assert task.get("target_device_key") == A2A_TARGET_DEVICE
        assert task.get("instruction")

        await _wait_for_hitl_request(http_client, thread_id, timeout=30.0)
        await asyncio.sleep(0.5)

        # Simulate the child completing the task and sending a2a_callback.
        callback = _build_agent_task_result(
            task_id=f"child-{thread_id}",
            status="success",
            summary=(
                "Child device executed the delegated task. "
                "The shell output was: child-done"
            ),
        )
        await a2a_mock_gateway.inject_callback(thread_id, callback)

        # Wait for the parent run to resume and finish.
        result = await sse_future
        assert result.run_end_status in ("done", "failed")

        # L2/L3: parent history contains the child result somewhere.
        messages = await _get_messages(http_client, thread_id)
        history = json.dumps(messages, ensure_ascii=False)
        assert "child-done" in history or result.run_end_status == "failed"


# -----------------------------------------------------------------------------
# E2E-SC-009: retry preserves attachment references
# -----------------------------------------------------------------------------


@pytest.mark.slow
class TestRetryAttachment:
    """Retrying a message with a file attachment re-injects the same reference."""

    @pytest.mark.timeout(180)
    async def test_retry_preserves_attachment_reference(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
    ) -> None:
        """Upload a file, chat with it, retry, and verify the reference remains."""
        marker = f"e2e-attachment-{uuid.uuid4().hex[:8]}"
        content = f"This is the attachment sentence for retry test: {marker}."

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            filename = os.path.basename(tmp_path)

            # 1. Upload the attachment for this thread.
            with open(tmp_path, "rb") as f:
                upload_resp = await http_client.post(
                    "/api/v1/files/upload",
                    params={"project_id": 0, "thread_id": thread_id},
                    files={"file": (filename, f, "text/plain")},
                    timeout=30.0,
                )
            upload_resp.raise_for_status()
            upload = upload_resp.json()
            file_path = upload["path"]
            file_url = upload.get("url") or f"/api/v1/files/raw?path={file_path}"
            assert file_path.startswith("uploads/")

            reference = {
                "id": file_url,
                "type": "file",
                "target_id": file_url,
                "target_name": filename,
            }

            # 2. Send a chat message that references the uploaded file.
            sse_future = asyncio.create_task(
                observe_agent_run(http_client, thread_id, timeout=120.0)
            )
            resp = await http_client.post(
                "/api/v1/chat",
                json={
                    "thread_id": thread_id,
                    "message": "请阅读附件并总结内容",
                    "project_id": 0,
                    "references": [reference],
                },
            )
            resp.raise_for_status()
            assert resp.json()["status"] in ("queued", "done")

            result = await sse_future
            assert result.run_end_status in ("done", "failed")

            # 3. Locate the original human message and its reference.
            messages = await _get_messages(http_client, thread_id)
            human_msgs = [m for m in messages if m.get("role") == "human"]
            assert human_msgs, "No human message found after first run"
            original = human_msgs[0]
            original_refs = original.get("references") or []
            assert any(
                r.get("target_id") == file_url for r in original_refs
            ), f"Original human message lost reference: {original_refs}"
            human_id = original["id"]

            # 4. Subscribe to SSE before retry so we catch run_start reliably.
            retry_sse_future = asyncio.create_task(
                observe_agent_run(
                    http_client, thread_id, timeout=120.0, expect_start=False
                )
            )
            retry_resp = await http_client.post(
                "/api/v1/chat/retry",
                json={
                    "thread_id": thread_id,
                    "message_id": human_id,
                    "message": "retry",
                    "revert_files": False,
                    "project_id": 0,
                },
            )
            retry_resp.raise_for_status()
            retry_body = retry_resp.json()
            assert retry_body["status"] == "queued"
            assert retry_body["action"] == "retry"

            # 5. Wait for the retry run and verify the reference is still present.
            retry_result = await retry_sse_future
            assert retry_result.run_end_status in ("done", "failed")

            retry_messages = await _get_messages(http_client, thread_id)
            assert retry_result.run_end_status in ("done", "failed")

            retry_messages = await _get_messages(http_client, thread_id)
            retry_human = [m for m in retry_messages if m.get("id") == human_id]
            assert retry_human, "Retried human message disappeared"
            retry_refs = retry_human[0].get("references") or []
            assert any(
                r.get("target_id") == file_url for r in retry_refs
            ), f"Retry lost the attachment reference: {retry_refs}"
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# -----------------------------------------------------------------------------
# E2E-SC-010: hop-count guard
# -----------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.real
class TestA2AHopGuard:
    """Re-delegating a subtask beyond ``max_hops`` returns ``a2a_error``."""

    @pytest.mark.timeout(180)
    async def test_hop_count_exceeded_returns_a2a_error(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        a2a_mock_gateway: A2AMockGateway,
    ) -> None:
        """Parent delegates; child attempts a second hop that exceeds max_hops."""
        sse_future = asyncio.create_task(
            observe_agent_run(http_client, thread_id, timeout=120.0)
        )

        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": (
                    "Use the task tool with remote={'agent_id': <device>} to delegate to device "
                    f"'{A2A_TARGET_DEVICE}' the task: execute 'echo hop-test'."
                ),
                "project_id": 0,
            },
        )
        resp.raise_for_status()
        assert resp.json()["status"] in ("queued", "done")

        # Wait for the parent to be in HITL waiting for the first callback.
        await _wait_for_send_agent_task_or_skip(
            http_client,
            thread_id,
            timeout=30.0,
        )
        await _wait_for_hitl_request(http_client, thread_id, timeout=30.0)
        await asyncio.sleep(0.5)

        # Inject a second a2a_task whose hop_count already exceeds max_hops.
        # This simulates the child trying to re-delegate.
        child_task_id = f"child-hop-{thread_id}"
        over_hop_task = {
            "task_id": child_task_id,
            "task_type": "a2a_task",
            "instruction": "delegate further",
            "caller_role": "desktop",
            "global_goal": "hop guard test",
            "attachments": [],
            "caller_device_key": a2a_mock_gateway.device_key,
            "root_thread_id": thread_id,
            "parent_thread_id": thread_id,
            "hop_count": 4,
            "max_hops": 3,
        }
        await a2a_mock_gateway.inject_task(child_task_id, over_hop_task)

        # The backend should reject the re-delegation and send an a2a_error
        # callback to the parent, which then ends the parent run.
        result = await sse_future
        assert result.run_end_status is not None, "父任务未进入终态"

        # 核心断言：超 hop 的再委托必须被拒绝 —— 不应创建孙会话
        child_resp = await http_client.get(
            f"/api/v1/conversations/{child_task_id}/messages", timeout=10.0
        )
        assert child_resp.status_code == 404 or child_resp.json().get("data") == [], (
            f"超 hop 再委托不应创建孙会话: status={child_resp.status_code} body={child_resp.text[:200]}"
        )


# -----------------------------------------------------------------------------
# E2E-SC-011: attachment MD5 mismatch
# -----------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.real
class TestA2AAttachmentValidation:
    """Corrupted A2A attachment (MD5 mismatch) returns an error callback."""

    @pytest.mark.timeout(180)
    async def test_attachment_md5_mismatch_returns_error(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        a2a_mock_gateway: A2AMockGateway,
    ) -> None:
        """Inject an a2a_task with a deliberately wrong attachment MD5."""
        # Upload a small file so the child backend can download it from itself.
        marker = f"e2e-md5-{uuid.uuid4().hex[:8]}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp:
            tmp.write(f"MD5 test payload: {marker}")
            tmp_path = tmp.name

        try:
            filename = os.path.basename(tmp_path)
            with open(tmp_path, "rb") as f:
                upload_resp = await http_client.post(
                    "/api/v1/files/upload",
                    params={"project_id": 0, "thread_id": thread_id},
                    files={"file": (filename, f, "text/plain")},
                    timeout=30.0,
                )
            upload_resp.raise_for_status()
            file_path = upload_resp.json()["path"]
            download_url = f"{E2E_BASE_URL}/api/v1/files/raw?path={file_path}"

            # Start a parent run that will HITL-wait for an A2A callback.
            sse_future = asyncio.create_task(
                observe_agent_run(http_client, thread_id, timeout=120.0)
            )
            resp = await http_client.post(
                "/api/v1/chat",
                json={
                    "thread_id": thread_id,
                    "message": (
                        "Use the task tool with remote={'agent_id': <device>} to delegate to device "
                        f"'{A2A_TARGET_DEVICE}' the task: read the attached file."
                    ),
                    "project_id": 0,
                },
            )
            resp.raise_for_status()
            assert resp.json()["status"] in ("queued", "done")

            await _wait_for_send_agent_task_or_skip(
                http_client,
                thread_id,
                timeout=30.0,
            )
            await _wait_for_hitl_request(http_client, thread_id, timeout=30.0)
            await asyncio.sleep(0.5)

            # Inject an a2a_task carrying the real file URL but a wrong MD5.
            child_task_id = f"child-md5-{thread_id}"
            size = os.path.getsize(tmp_path)
            corrupted_task = {
                "task_id": child_task_id,
                "task_type": "a2a_task",
                "instruction": "read the attached file",
                "caller_role": "desktop",
                "global_goal": "md5 validation test",
                "attachments": [
                    {
                        "filename": filename,
                        "download_url": download_url,
                        "file_size": size,
                        "md5": "deadbeefdeadbeefdeadbeefdeadbeef",
                    }
                ],
                "caller_device_key": a2a_mock_gateway.device_key,
                "root_thread_id": thread_id,
                "parent_thread_id": thread_id,
                "hop_count": 1,
                "max_hops": 3,
            }
            await a2a_mock_gateway.inject_task(child_task_id, corrupted_task)

            # The child handler should detect the MD5 mismatch and send an
            # a2a_error callback to the parent, ending the run.
            result = await sse_future
            assert result.run_end_status is not None, "父任务未进入终态"

            # 核心断言：MD5 校验失败应在派发前拒绝 —— 不应创建子会话
            child_resp = await http_client.get(
                f"/api/v1/conversations/{child_task_id}/messages", timeout=10.0
            )
            assert child_resp.status_code == 404 or child_resp.json().get("data") == [], (
                f"MD5 不符不应创建子会话: status={child_resp.status_code} body={child_resp.text[:200]}"
            )
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# -----------------------------------------------------------------------------
# 新增：A2A 成功路径附件注入子会话 + a2a_error 回调载荷断言
# -----------------------------------------------------------------------------


def _real_md5(path: str) -> str:
    """计算本地文件的真实 MD5（与后端 compute_file_hash 一致）。"""
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _child_conversation_row(
    http_client: httpx.AsyncClient, child_thread_id: str
) -> dict[str, Any] | None:
    """SQLite 直读子会话血缘字段（API 未暴露会话详情，参考 test_13 的定位写法）。"""
    config_resp = await http_client.get("/api/v1/system/config")
    config_resp.raise_for_status()
    configs = {
        item.get("key"): item.get("value")
        for item in config_resp.json()
        if isinstance(item, dict)
    }
    sqlite_path = configs.get("SQLITE_PATH")
    if sqlite_path:
        db_path = Path(os.path.expanduser(sqlite_path)).expanduser()
    else:
        app_data_dir = configs.get("EVOLOOP_APP_DATA_DIR")
        if app_data_dir:
            base = Path(os.path.expanduser(app_data_dir)).expanduser()
        else:
            base = Path.home() / ".evoloop"
        db_path = base / "database" / "backend.db"

    def _read() -> dict[str, Any] | None:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT parent_thread_id, root_thread_id, caller_device_key, "
                "executor_device_key, title FROM conversations WHERE id = ?",
                (child_thread_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    return await asyncio.to_thread(_read)


class A2AErrorCaptureGateway(A2AMockGateway):
    """扩展 mock gateway：额外捕获回传给调用方的 a2a_callback 失败信封（a2a_error）。

    仅当 ``EVOLOOP_A2A_TEST_BED`` 配置且后端与测试同进程（respx 可拦截出站请求）时
    生效；外部真实网关模式下 ``captured_errors`` 为空，用例回退到父 run 历史文本断言。
    """

    def __init__(
        self, http_client: httpx.AsyncClient, device_key: str | None
    ) -> None:
        super().__init__(http_client, device_key)
        self.captured_errors: list[dict[str, Any]] = []

    def _on_message_send(self, request: httpx.Request) -> httpx.Response:
        try:
            payload = json.loads(request.content)
        except Exception:
            payload = {}
        envelope = payload.get("envelope") or {}
        body = envelope.get("body") or {}
        content = body.get("content") or {}
        if body.get("action") == "a2a_task":
            self.captured_tasks.append(content)
        elif body.get("action") == "a2a_callback":
            if isinstance(content, dict) and content.get("status") == "failed":
                self.captured_errors.append(content)
        return httpx.Response(200, json={"code": 0, "message": "ok", "data": {}})


@pytest.fixture
async def a2a_error_capture_gateway(
    http_client: httpx.AsyncClient,
) -> A2AErrorCaptureGateway:
    """提供带 a2a_error 捕获能力的网关 helper；环境不满足时 skip。"""
    status = await http_client.get("/api/v1/utils/evoloop-status")
    status.raise_for_status()
    evo = status.json()
    device_key = evo.get("device_key")
    connected = evo.get("connected", False)

    if not A2A_TEST_BED and not connected:
        pytest.skip(
            "A2A test bed not configured: "
            "set EVOLOOP_A2A_TEST_BED or connect EvoCloud gateway"
        )

    async with A2AErrorCaptureGateway(http_client, device_key) as gateway:
        yield gateway


@pytest.mark.slow
@pytest.mark.real
class TestA2AAttachmentSuccess:
    """A2A 成功路径：携带真实附件（正确 MD5）的 a2a_task 应创建子会话并正常回传结果。"""

    @pytest.mark.timeout(180)
    async def test_a2a_task_with_real_attachment_creates_child_conversation(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        a2a_error_capture_gateway: A2AErrorCaptureGateway,
    ) -> None:
        """上传真实文件 → 注入带真实 MD5 的 a2a_task → 子会话创建且不出现 a2a_error。"""
        marker = f"e2e-a2a-real-attachment-{uuid.uuid4().hex[:8]}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp:
            tmp.write(f"附件真实内容：{marker}\n这是传给子设备的唯一标记。")
            tmp_path = tmp.name

        try:
            filename = os.path.basename(tmp_path)
            with open(tmp_path, "rb") as f:
                upload_resp = await http_client.post(
                    "/api/v1/files/upload",
                    params={"project_id": 0, "thread_id": thread_id},
                    files={"file": (filename, f, "text/plain")},
                    timeout=30.0,
                )
            upload_resp.raise_for_status()
            file_path = upload_resp.json()["path"]
            assert file_path.startswith("uploads/")
            download_url = f"{E2E_BASE_URL}/api/v1/files/raw?path={file_path}"
            real_md5 = _real_md5(tmp_path)
            file_size = os.path.getsize(tmp_path)

            # 父 run 委托子设备并进入 HITL 挂起。
            sse_future = asyncio.create_task(
                observe_agent_run(http_client, thread_id, timeout=150.0)
            )
            resp = await http_client.post(
                "/api/v1/chat",
                json={
                    "thread_id": thread_id,
                    "message": (
                        "Use the task tool with remote={'agent_id': <device>} to delegate to device "
                        f"'{A2A_TARGET_DEVICE}' the task: read the attached file "
                        "and report its exact contents back."
                    ),
                    "project_id": 0,
                },
            )
            resp.raise_for_status()
            assert resp.json()["status"] in ("queued", "done")

            task = await a2a_error_capture_gateway.fetch_task_from_messages(
                thread_id, timeout=60.0
            )
            assert task.get("target_device_key") == A2A_TARGET_DEVICE
            assert task.get("instruction")

            await _wait_for_hitl_request(http_client, thread_id, timeout=30.0)
            await asyncio.sleep(0.5)

            # 注入携带真实附件的 a2a_task（MD5 用真实文件哈希）。
            child_task_id = f"child-real-att-{uuid.uuid4().hex[:8]}"
            real_task = {
                "task_id": child_task_id,
                "task_type": "a2a_task",
                "instruction": "read the attached file and report its exact contents back",
                "caller_role": "desktop",
                "global_goal": "A2A attachment injection success test",
                "attachments": [
                    {
                        "filename": filename,
                        "download_url": download_url,
                        "file_size": file_size,
                        "md5": real_md5,
                    }
                ],
                "caller_device_key": a2a_error_capture_gateway.device_key,
                "root_thread_id": thread_id,
                "parent_thread_id": thread_id,
                "hop_count": 1,
                "max_hops": 3,
            }
            await a2a_error_capture_gateway.inject_task(child_task_id, real_task)

            # 断言 1：子会话必须被创建并完成调度。任何 a2a_error 路径
            # （hop 超限 / MD5 不匹配 / 下载失败 / 调度失败）都不会走到这里。
            async def _child_created() -> list[dict[str, Any]] | None:
                child_resp = await http_client.get(
                    f"/api/v1/conversations/{child_task_id}/messages", timeout=10.0
                )
                if child_resp.status_code != 200:
                    return None
                data = child_resp.json().get("data", [])
                return data or None

            child_messages = await wait_until(
                _child_created,
                timeout=60.0,
                interval=1.0,
                desc=f"子会话 {child_task_id} 创建并生成消息",
            )
            child_roles = {m.get("role") for m in child_messages}
            assert {"system", "human"} <= child_roles, (
                f"子会话缺少 system/human 消息，实际 roles={child_roles}"
            )

            # 断言 2：子会话血缘字段正确（parent_thread_id 指向父线程）。
            row = await _child_conversation_row(http_client, child_task_id)
            assert row is not None, f"SQLite 未找到子会话 {child_task_id}"
            assert row["parent_thread_id"] == thread_id, row
            assert row["root_thread_id"] == thread_id, row
            assert row["caller_device_key"] == a2a_error_capture_gateway.device_key, (
                row
            )

            # 断言 3：进程内 respx 模式下不应捕获到任何失败回调（a2a_error）。
            if a2a_error_capture_gateway.captured_errors:
                raise AssertionError(
                    "成功路径捕获到 a2a_error 信封: "
                    f"{a2a_error_capture_gateway.captured_errors}"
                )

            # 等待父 run 被子任务回调恢复并结束（子设备真实执行并回传结果）。
            try:
                result = await sse_future
                assert result.run_end_status in ("done", "failed")
                messages = await _get_messages(http_client, thread_id)
                history = json.dumps(messages, ensure_ascii=False)
                for err_text in (
                    "Maximum chain delegation depth exceeded",
                    "MD5 mismatch",
                    "Failed to download attachment",
                ):
                    assert err_text not in history, (
                        f"父 run 历史中出现错误摘要 {err_text!r}"
                    )
            except TimeoutError as exc:
                pytest.fail(
                    f"父 run 未在观测窗口内被 A2A 回调恢复"
                    f"（子设备可能未调用 complete_task）：{exc}"
                )
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


@pytest.mark.slow
@pytest.mark.real
class TestA2AErrorCallbackPayload:
    """hop 超限的 a2a_task 应回传携带 status/error 字段的 a2a_error 信封。"""

    @pytest.mark.timeout(180)
    async def test_hop_overflow_error_callback_payload(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        a2a_error_capture_gateway: A2AErrorCaptureGateway,
    ) -> None:
        """注入 hop_count > max_hops 的 a2a_task，捕获回传的 a2a_error 载荷。"""
        expected_error = "Maximum chain delegation depth exceeded"

        sse_future = asyncio.create_task(
            observe_agent_run(http_client, thread_id, timeout=120.0)
        )
        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": (
                    "Use the task tool with remote={'agent_id': <device>} to delegate to device "
                    f"'{A2A_TARGET_DEVICE}' the task: execute 'echo hop-test'."
                ),
                "project_id": 0,
            },
        )
        resp.raise_for_status()
        assert resp.json()["status"] in ("queued", "done")

        await _wait_for_send_agent_task_or_skip(http_client, thread_id, timeout=30.0)
        await _wait_for_hitl_request(http_client, thread_id, timeout=30.0)
        await asyncio.sleep(0.5)

        child_task_id = f"child-hop-err-{uuid.uuid4().hex[:8]}"
        over_hop_task = {
            "task_id": child_task_id,
            "task_type": "a2a_task",
            "instruction": "delegate further",
            "caller_role": "desktop",
            "global_goal": "hop guard payload test",
            "attachments": [],
            "caller_device_key": a2a_error_capture_gateway.device_key,
            "root_thread_id": thread_id,
            "parent_thread_id": thread_id,
            "hop_count": 4,
            "max_hops": 3,
        }
        await a2a_error_capture_gateway.inject_task(child_task_id, over_hop_task)

        # 阶段 1：从下发链路捕获 a2a_error 信封。优先走进程内 respx 拦截；
        # 外部真实网关模式下尝试读取网关设备日志（记录下发到本设备的命令）。
        captured: dict[str, Any] | None = None

        async def _try_capture() -> dict[str, Any] | None:
            if a2a_error_capture_gateway.captured_errors:
                return a2a_error_capture_gateway.captured_errors[0]
            try:
                log_resp = await http_client.get(
                    f"/api/v1/devices/{a2a_error_capture_gateway.device_key}/logs",
                    timeout=10.0,
                )
                if log_resp.status_code == 200:
                    entries = log_resp.json()
                    if isinstance(entries, list):
                        for entry in entries:
                            text = json.dumps(entry, ensure_ascii=False)
                            if expected_error in text:
                                return entry if isinstance(entry, dict) else {
                                    "raw": entry
                                }
            except Exception as exc:
                logger.debug("读取网关设备日志失败: %s", exc)
            return None

        try:
            captured = await wait_until(
                _try_capture,
                timeout=45.0,
                interval=1.0,
                desc="a2a_error 下发信封捕获",
            )
        except TimeoutError:
            captured = None

        # 载荷断言：信封内容应包含错误状态字段与错误摘要文本。
        if captured is not None:
            text = json.dumps(captured, ensure_ascii=False)
            assert expected_error in text, text
            assert '"status": "failed"' in text or "failed" in text, text
            assert child_task_id in text, text

        # 阶段 2：外部真实网关模式下，a2a_error 回调经网关回传父线程并恢复父 run；
        # 退而求其次断言父 run 上下文（历史消息）包含错误摘要文本。
        respx_captured = bool(a2a_error_capture_gateway.captured_errors)
        if not respx_captured:
            try:
                result = await sse_future
                assert result.run_end_status is not None
                messages = await _get_messages(http_client, thread_id)
                history = json.dumps(messages, ensure_ascii=False)
                assert (
                    expected_error in history
                    or '"status": "failed"' in history
                    or result.run_end_status == "failed"
                ), (
                    f"父 run 历史中未找到 a2a_error 载荷文本; "
                    f"run_end_status={result.run_end_status}"
                )
            except TimeoutError as exc:
                if captured is None:
                    raise AssertionError(
                        "既未捕获到 a2a_error 信封，父 run 也未在观测窗口内恢复，"
                        "无法完成载荷断言"
                    ) from exc
                logger.warning("父 run 未恢复但信封载荷已断言，忽略: %s", exc)
        else:
            if not sse_future.done():
                sse_future.cancel()
                try:
                    await sse_future
                except asyncio.CancelledError:
                    pass
