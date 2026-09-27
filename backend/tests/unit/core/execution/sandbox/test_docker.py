"""Unit tests for DockerSandbox (docker client mocked)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.core.execution.sandbox.base import Sandbox
from app.core.execution.sandbox.docker import (
    DockerSandbox,
    DockerSandboxProcess,
    _to_container_path,
)
from app.core.execution.sandbox.local import LocalSandbox


def _make_sandbox() -> DockerSandbox:
    sb = DockerSandbox.__new__(DockerSandbox)
    sb.image_name = "evoloop-sandbox"
    sb.client = MagicMock()
    sb.container_name = "evoloop-sandbox-runtime"
    sb.container = MagicMock()
    sb.container.id = "container-1"
    sb.workspace_root = "/ws"
    return sb


def test_to_container_path_translation():
    assert _to_container_path("/ws", "/ws") == "/workspace"
    assert _to_container_path("/ws/sub", "/ws") == "/workspace/sub"
    assert _to_container_path("/ws/sub/deep", "/ws") == "/workspace/sub/deep"
    assert _to_container_path("/outside", "/ws") is None


async def test_sandbox_process_wait_returns_exit_code():
    client = MagicMock()
    client.api.exec_inspect.return_value = {"Running": False, "ExitCode": 3, "Pid": 123}

    stream_task = asyncio.create_task(asyncio.sleep(0))
    proc = DockerSandboxProcess(client, "container-1", "exec-1", stream_task)
    assert await proc.wait(5) == 3
    assert proc.pid == 123


async def test_sandbox_process_wait_raises_timeout():
    client = MagicMock()
    client.api.exec_inspect.return_value = {"Running": True}

    stream_task = asyncio.create_task(asyncio.sleep(0))
    proc = DockerSandboxProcess(client, "container-1", "exec-1", stream_task)
    with pytest.raises(asyncio.TimeoutError):
        await proc.wait(0.2)


async def test_sandbox_process_kill_signals_pid_tree():
    client = MagicMock()
    client.api.exec_inspect.return_value = {"Running": True, "Pid": 777}
    container = MagicMock()
    client.containers.get.return_value = container

    proc = DockerSandboxProcess(client, "container-1", "exec-1", asyncio.create_task(asyncio.sleep(0)))
    proc.kill()

    client.containers.get.assert_called_once_with("container-1")
    container.exec_run.assert_any_call(["kill", "-s", "KILL", "777"])
    container.exec_run.assert_any_call(["pkill", "-s", "KILL", "-P", "777"])


async def test_sandbox_process_kill_noop_without_pid():
    client = MagicMock()
    client.api.exec_inspect.return_value = {"Running": True, "Pid": None}

    proc = DockerSandboxProcess(client, "container-1", "exec-1", asyncio.create_task(asyncio.sleep(0)))
    proc.kill()
    client.containers.get.assert_not_called()


async def test_spawn_wires_exec_and_returns_process():
    sb = _make_sandbox()
    sb.client.api.exec_create.return_value = {"Id": "exec-1"}
    sb.client.api.exec_start.return_value = iter([])

    process = await sb.spawn("echo hi")

    sb.client.api.exec_create.assert_called_once()
    assert isinstance(process, DockerSandboxProcess)
    assert process._exec_id == "exec-1"


async def test_spawn_applies_container_working_dir():
    sb = _make_sandbox()
    sb.client.api.exec_create.return_value = {"Id": "exec-1"}
    sb.client.api.exec_start.return_value = iter([])

    await sb.spawn("pwd", working_dir="/ws/sub")

    cmd = sb.client.api.exec_create.call_args.args[1]
    assert cmd == ["/bin/sh", "-c", "cd /workspace/sub && pwd"]


async def test_spawn_rejects_path_outside_workspace():
    sb = _make_sandbox()
    with pytest.raises(RuntimeError, match="outside WORKSPACE_ROOT"):
        await sb.spawn("pwd", working_dir="/outside")


@pytest.fixture
def _reset_factory():
    from app.core.execution.sandbox.factory import SandboxFactory

    SandboxFactory.reset()
    yield
    SandboxFactory.reset()


async def test_factory_falls_back_to_local_when_docker_init_fails(_reset_factory):
    with (
        patch("app.core.config.settings.EXECUTION_MODE", "docker"),
        patch(
            "app.core.execution.sandbox.docker.DockerSandbox",
            side_effect=RuntimeError("no docker daemon"),
        ),
    ):
        from app.core.execution.sandbox.factory import SandboxFactory

        sandbox = await SandboxFactory.get_sandbox()
    assert isinstance(sandbox, LocalSandbox)
    assert isinstance(sandbox, Sandbox)
