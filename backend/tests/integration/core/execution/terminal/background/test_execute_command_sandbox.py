"""Integration tests for execute_command sandbox boundaries.

These tests run in-process and spawn real subprocesses to verify that:
- ``~/.evoloop`` ( EvoLoop app data dir) is treated as a safe root.
- Commands that try to ``cd`` outside allowed roots are blocked.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.execution.terminal.background.runner import execute_smart

PROJECT_DIR = str(Path(__file__).parents[5])


@pytest.mark.asyncio
class TestExecuteCommandSandbox:
    async def test_execute_smart_allows_cd_to_evoloop(self):
        """cd into a temp directory under ~/.evoloop should succeed."""
        app_data = os.path.expanduser(settings.EVOLOOP_APP_DATA_DIR)
        os.makedirs(app_data, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=app_data, prefix="test_exec_") as tmpdir:
            config = {"configurable": {"working_directory": PROJECT_DIR}}
            command = f"cd {tmpdir} && pwd"
            result = await execute_smart(command, timeout=10, config=config)

            assert "Security Error" not in result, f"Unexpected block: {result}"
            # pwd output uses the real path
            assert os.path.realpath(tmpdir) in result

    async def test_execute_smart_blocks_cd_to_disallowed_path(self):
        """cd into /tmp from the project working dir should be blocked."""
        config = {"configurable": {"working_directory": PROJECT_DIR}}
        result = await execute_smart("cd /tmp && pwd", timeout=10, config=config)

        assert "Security Error" in result
        assert "允许的工作目录之外" in result

    async def test_execute_smart_allows_absolute_script_path_under_evoloop(self):
        """Running a script by absolute path under ~/.evoloop should not be blocked."""
        app_data = os.path.expanduser(settings.EVOLOOP_APP_DATA_DIR)
        os.makedirs(app_data, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=app_data, prefix="test_exec_") as tmpdir:
            script = os.path.join(tmpdir, "hello.py")
            with open(script, "w", encoding="utf-8") as f:
                f.write('print("hello-from-evoloop")')

            config = {"configurable": {"working_directory": PROJECT_DIR}}
            command = f"python3 {script}"
            result = await execute_smart(command, timeout=10, config=config)

            assert "Security Error" not in result, f"Unexpected block: {result}"
            assert "hello-from-evoloop" in result
