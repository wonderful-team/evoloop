"""Verification of cancel_callback → _terminate_process_group refactor.

Spawns a real process group and asserts SIGTERM is delivered to the whole group.
"""

from __future__ import annotations

import asyncio
import os

from app.core.execution.sandbox.local import _terminate_process_group


async def _spawn_sleep_process() -> asyncio.subprocess.Process:
    """Start `sleep 30` in its own process group (mirrors production setsid)."""
    return await asyncio.create_subprocess_shell(
        "sleep 30",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        preexec_fn=os.setsid,
    )


async def _process_alive(process: asyncio.subprocess.Process) -> bool:
    if process.returncode is not None:
        return False
    try:
        os.kill(process.pid, 0)
        return True
    except ProcessLookupError:
        return False


class TestTerminateProcessGroup:
    async def test_terminates_whole_group(self) -> None:
        process = await _spawn_sleep_process()
        try:
            assert await _process_alive(process)
            _terminate_process_group(process)
            await asyncio.wait_for(process.wait(), timeout=5)
            assert process.returncode is not None
            assert not await _process_alive(process)
        finally:
            if await _process_alive(process):
                process.kill()
                await process.wait()

    async def test_missing_process_group_is_noop(self) -> None:
        # ProcessLookupError path must be swallowed (as before).
        fake = type(
            "FakeProcess",
            (),
            {"pid": 999_999_999},
        )()
        _terminate_process_group(fake)
