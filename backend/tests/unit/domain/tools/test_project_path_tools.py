"""Verify execute_command, code exploration tools, and wiki tools use correct project path."""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from app.constants import DEFAULT_PROJECT_ID
from app.core.context import ContextManager, EvoContext
from app.domain.tools.execution import _execute_command
from app.domain.tools.wiki_tools import _resolve_project_path


@pytest.fixture
def project_workspace():
    with tempfile.TemporaryDirectory() as workspace:
        project_path = os.path.join(workspace, "evoloop")
        os.makedirs(project_path, exist_ok=True)
        yield workspace, project_path


def _set_ctx(project_path=None, project_id=None):
    return ContextManager.set(
        EvoContext(
            working_directory=project_path,
            project_id=project_id,
            thread_id="test-thread",
        )
    )


@pytest.mark.asyncio
async def test_execute_command_uses_project_cwd(project_workspace):
    """execute_command should cd into project directory in project mode."""
    workspace, project_path = project_workspace
    token = _set_ctx(project_path, project_id=57)
    try:
        with patch("app.core.execution.sandbox.factory.SandboxFactory.get_sandbox") as mock_get_sandbox:
            mock_sandbox = MagicMock()
            mock_sandbox.run_command = MagicMock(return_value=("", "", 0))
            mock_get_sandbox.return_value = mock_sandbox

            await _execute_command("pwd")

            called_command = mock_sandbox.run_command.call_args.args[0]
            assert f"cd {project_path} && pwd" == called_command
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_execute_command_global_mode_uses_workspace_root(project_workspace):
    """execute_command should cd into WORKSPACE_ROOT in global mode."""
    workspace, project_path = project_workspace
    token = _set_ctx(None, project_id=DEFAULT_PROJECT_ID)
    try:
        with patch(
            "app.domain.tools.execution.execute.SystemConfigService.get_value",
            return_value=workspace,
        ), patch("app.core.execution.sandbox.factory.SandboxFactory.get_sandbox") as mock_get_sandbox:
            mock_sandbox = MagicMock()
            mock_sandbox.run_command = MagicMock(return_value=("", "", 0))
            mock_get_sandbox.return_value = mock_sandbox

            await _execute_command("pwd")

            called_command = mock_sandbox.run_command.call_args.args[0]
            assert f"cd {workspace} && pwd" == called_command
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_execute_command_respects_working_directory_config(project_workspace):
    """execute_command should use working_directory from RunnableConfig if EvoContext is empty."""
    workspace, project_path = project_workspace
    token = _set_ctx(None, None)
    try:
        with patch("app.core.execution.sandbox.factory.SandboxFactory.get_sandbox") as mock_get_sandbox:
            mock_sandbox = MagicMock()
            mock_sandbox.run_command = MagicMock(return_value=("", "", 0))
            mock_get_sandbox.return_value = mock_sandbox

            config = RunnableConfig(configurable={"working_directory": project_path})
            await _execute_command("pwd", config=config)

            called_command = mock_sandbox.run_command.call_args.args[0]
            assert f"cd {project_path} && pwd" == called_command
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_find_symbol_uses_project_repo_path(project_workspace):
    """find_symbol should pass project working_directory as repo_path to engine."""
    workspace, project_path = project_workspace
    token = _set_ctx(project_path, project_id=57)
    try:
        with patch(
            "app.domain.codebase.exploration.tools.get_exploration_engine"
        ) as mock_get_engine:
            mock_engine = AsyncMock()
            mock_engine.find_symbol = AsyncMock(return_value={
                "source": "grep",
                "results": [{"file_path": "main.py", "line": 1, "content": "x"}],
            })
            mock_get_engine.return_value = mock_engine

            from app.domain.codebase.exploration.tools import find_symbol
            config = RunnableConfig(configurable={"project_id": 57})
            await find_symbol.ainvoke(
                {"name": "foo"},
                config=config,
            )

            call_args = mock_engine.find_symbol.call_args.args
            assert call_args[1] == 57
            assert call_args[2] == project_path
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_ask_codebase_fallback_uses_project_repo_path(project_workspace):
    """ask_codebase fallback code search should use project working_directory as repo_path."""
    workspace, project_path = project_workspace
    token = _set_ctx(project_path, project_id=57)
    try:
        with patch(
            "app.domain.codebase.exploration.tools.get_exploration_engine"
        ) as mock_get_engine, patch(
            "app.core.memory.lifespan.MemoryLifespanManager.is_initialized",
            return_value=True,
        ), patch(
            "app.core.memory.lifespan.MemoryLifespanManager.get_container"
        ) as mock_get_container:
            mock_manager = MagicMock()
            mock_manager.search_concepts_data = AsyncMock(return_value=[])
            mock_container = MagicMock()
            mock_container.memory_manager = mock_manager
            mock_get_container.return_value = mock_container

            mock_engine = AsyncMock()
            mock_engine.search_code = AsyncMock(return_value=[
                {"file_path": "main.py", "line": 1, "content": "x"}
            ])
            mock_get_engine.return_value = mock_engine

            from app.domain.codebase.exploration.tools import ask_codebase
            await ask_codebase.ainvoke(
                {"question": "how does x work"},
                config=RunnableConfig(configurable={}),
            )

            call_args = mock_engine.search_code.call_args.args
            assert call_args[2] == project_path
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_wiki_resolve_project_path_uses_working_directory(project_workspace):
    """wiki_tools._resolve_project_path should return project working_directory."""
    workspace, project_path = project_workspace
    token = _set_ctx(project_path, project_id=57)
    try:
        config = RunnableConfig(configurable={})
        result = _resolve_project_path(config)
        assert result == project_path
    finally:
        ContextManager.reset(token)
