"""Unit tests for LocalSandbox async spawn/streaming/cancel."""

from __future__ import annotations

import asyncio
import os

import pytest

from app.core.execution.sandbox.base import Sandbox
from app.core.execution.sandbox.factory import SandboxFactory
from app.core.execution.sandbox.local import LocalSandbox


@pytest.fixture(autouse=True)
def _reset_factory_singleton():
    SandboxFactory.reset()
    yield
    SandboxFactory.reset()


async def test_spawn_streams_output_and_returns_exit_code():
    sandbox = LocalSandbox()
    chunks: list[str] = []
    stdout_buf: list[str] = []
    process = await sandbox.spawn(
        "echo hello\n",
        on_output=chunks.append,
        stdout_buf=stdout_buf,
    )

    exit_code = await process.wait(10)
    assert exit_code == 0
    assert "hello" in "".join(chunks)
    assert "hello\n" in "".join(stdout_buf)
    assert process.pid is not None


async def test_spawn_captures_stderr_with_prefix():
    sandbox = LocalSandbox()
    chunks: list[str] = []
    stderr_buf: list[str] = []
    process = await sandbox.spawn(
        "echo boom 1>&2",
        on_output=chunks.append,
        stderr_buf=stderr_buf,
    )

    exit_code = await process.wait(10)
    assert exit_code == 0
    assert "[stderr] boom" in "".join(chunks)
    assert "boom\n" in "".join(stderr_buf)


async def test_spawn_nonzero_exit_code():
    sandbox = LocalSandbox()
    process = await sandbox.spawn("exit 3")
    assert await process.wait(10) == 3


async def test_spawn_applies_working_dir(tmp_path):
    sandbox = LocalSandbox()
    stdout_buf: list[str] = []
    process = await sandbox.spawn("pwd", working_dir=str(tmp_path), stdout_buf=stdout_buf)

    exit_code = await process.wait(10)
    assert exit_code == 0
    assert os.path.realpath(str(tmp_path)) in "".join(stdout_buf)


async def test_spawn_timeout_raises_and_kill_terminates():
    sandbox = LocalSandbox()
    process = await sandbox.spawn("sleep 30")

    with pytest.raises(asyncio.TimeoutError):
        await process.wait(0.3)

    process.kill()
    exit_code = await asyncio.wait_for(process.wait(5), timeout=5)
    assert exit_code != 0


async def test_factory_returns_local_sandbox_by_default():
    sandbox = await SandboxFactory.get_sandbox()
    assert isinstance(sandbox, Sandbox)
    assert isinstance(sandbox, LocalSandbox)
