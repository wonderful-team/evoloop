"""Real docker-environment smoke test for the Docker sandbox.

Requires a running docker daemon and the `evoloop-sandbox` image.
Run: .venv/bin/python -m pytest tests/real/test_docker_sandbox_real.py -v -s
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.core.execution.sandbox.factory import SandboxFactory
from app.core.execution.terminal.background import (
    CreateBackgroundTaskRequest,
    TaskStatus,
    TaskType,
    task_manager,
)
from app.core.execution.terminal.background.runner import (
    execute_smart,
    run_command_background,
)


def _require_docker():
    try:
        import docker

        docker.from_env().ping()
    except Exception as e:
        pytest.skip(f"docker unavailable: {e}")


@pytest.fixture(scope="session")
def _shared_workspace(tmp_path_factory):
    ws = tmp_path_factory.mktemp("evoloop-ws") / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "subdir").mkdir(exist_ok=True)
    return str(ws)


@pytest.fixture(autouse=True)
def _docker_env(_shared_workspace):
    _require_docker()
    settings.EXECUTION_MODE = "docker"
    # WORKSPACE_ROOT is fixed at container creation; share one workspace across
    # tests so the bind mount stays valid.
    with patch(
        "app.core.project.utils.get_workspace_root",
        return_value=_shared_workspace,
    ):
        SandboxFactory.reset()
        yield
        SandboxFactory.reset()


@pytest.fixture(autouse=True)
def _mock_events():
    with (
        patch("app.core.events.system_bus.publish", new=AsyncMock()),
        patch(
            "app.core.monitoring.activity.activity_monitor.record_task_update",
            new=AsyncMock(),
        ),
    ):
        yield


@pytest.mark.real
async def test_docker_execute_smart_runs_in_container():
    host_hostname = (await asyncio.to_thread(__import__, "socket")).gethostname()

    result = await execute_smart("hostname", timeout=60, config=None)

    # Real container execution: the hostname must be the container's, not the host's.
    assert "Security Error" not in result, result
    container_hostname = result.strip().splitlines()[-1]
    assert container_hostname
    assert container_hostname != host_hostname, (
        f"command ran on host, not in container: {result!r}"
    )


@pytest.mark.real
async def test_docker_execute_smart_streams_output():
    result = await execute_smart(
        "printf 'line1\\nline2\\n'", timeout=60, config=None
    )
    assert "line1" in result
    assert "line2" in result


@pytest.mark.real
async def test_docker_run_command_background_completes():
    task = await task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title="echo bg",
            tool_name="execute_command",
            thread_id="real-t1",
        )
    )
    await run_command_background(task, "echo docker-bg-ok", timeout=30, config=None)

    assert task.status is TaskStatus.COMPLETED
    assert "docker-bg-ok" in task.get_recent_output()


@pytest.mark.real
async def test_docker_working_dir_translation(_shared_workspace):
    sub = os.path.join(_shared_workspace, "subdir")

    result = await execute_smart(
        "pwd", timeout=60, config={"configurable": {"working_directory": sub}}
    )
    assert "/workspace/subdir" in result, f"wrong container cwd: {result!r}"


@pytest.mark.real
async def test_docker_timeout_kills_process():
    task = await task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title="sleep 30",
            tool_name="execute_command",
            thread_id="real-t1",
        )
    )
    await run_command_background(task, "sleep 30", timeout=2, config=None)

    assert task.status is TaskStatus.TIMEOUT
