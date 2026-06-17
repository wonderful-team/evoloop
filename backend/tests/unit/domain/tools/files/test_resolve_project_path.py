"""Verify all file tools resolve relative paths against project working directory."""

import os
import tempfile

import pytest
from langchain_core.runnables import RunnableConfig

from app.core.context import ContextManager, EvoContext
from app.domain.tools.files.delete_file import delete_file
from app.domain.tools.files.edit_file import edit_file
from app.domain.tools.files.find_files import find_files
from app.domain.tools.files.grep_search import grep_search_internal
from app.domain.tools.files.list_dir import handle_list
from app.domain.tools.files.move_file import move_file
from app.domain.tools.files.read_file import handle_read
from app.domain.tools.files.utils import resolve_and_validate_path
from app.domain.tools.files.write_file import handle_write


@pytest.fixture
def project_workspace():
    with tempfile.TemporaryDirectory() as workspace:
        project_path = os.path.join(workspace, "evoloop")
        os.makedirs(project_path, exist_ok=True)
        with open(os.path.join(project_path, "README.md"), "w", encoding="utf-8") as f:
            f.write("# Evoloop\n")
        with open(os.path.join(project_path, "main.py"), "w", encoding="utf-8") as f:
            f.write("print('hello')\n")
        yield workspace, project_path


def _set_ctx(project_path):
    return ContextManager.set(
        EvoContext(working_directory=project_path, thread_id="test-thread")
    )


@pytest.mark.asyncio
async def test_resolve_and_validate_path_uses_project_cwd(project_workspace):
    workspace, project_path = project_workspace
    token = _set_ctx(project_path)
    try:
        result = await resolve_and_validate_path("README.md")
        assert result == os.path.join(project_path, "README.md")
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_resolve_and_validate_path_does_not_fall_back_to_workspace_root(
    project_workspace,
):
    workspace, project_path = project_workspace
    with open(os.path.join(workspace, "README.md"), "w", encoding="utf-8") as f:
        f.write("# Workspace Root\n")

    token = _set_ctx(project_path)
    try:
        result = await resolve_and_validate_path("README.md")
        assert result == os.path.join(project_path, "README.md")
        with open(result, encoding="utf-8") as f:
            assert "Evoloop" in f.read()
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_list_dir_in_project_mode(project_workspace):
    workspace, project_path = project_workspace
    token = _set_ctx(project_path)
    try:
        output, meta = await handle_list(".", config=RunnableConfig(configurable={}))
        assert "README.md" in output
        assert meta["count"] >= 1
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_read_file_in_project_mode(project_workspace):
    workspace, project_path = project_workspace
    token = _set_ctx(project_path)
    try:
        result, meta = await handle_read("README.md", config=RunnableConfig(configurable={}))
        assert "Evoloop" in result
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_write_file_in_project_mode(project_workspace):
    workspace, project_path = project_workspace
    token = _set_ctx(project_path)
    try:
        result = await handle_write(
            action="create",
            path="new_file.py",
            content="x = 1\n",
            config=RunnableConfig(configurable={}),
        )
        assert os.path.exists(os.path.join(project_path, "new_file.py"))
        assert "Workspace Root" not in result
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_edit_file_in_project_mode(project_workspace):
    workspace, project_path = project_workspace
    token = _set_ctx(project_path)
    try:
        await edit_file.ainvoke(
            {
                "path": "main.py",
                "target": "hello",
                "replacement": "world",
                "verify_types": False,
            },
            config=RunnableConfig(configurable={}),
        )
        assert os.path.exists(os.path.join(project_path, "main.py"))
        with open(os.path.join(project_path, "main.py"), encoding="utf-8") as f:
            content = f.read()
        assert "world" in content
        assert "hello" not in content
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_grep_search_in_project_mode(project_workspace):
    workspace, project_path = project_workspace
    token = _set_ctx(project_path)
    try:
        output, meta = await grep_search_internal(
            pattern="Evoloop",
            path=".",
            config=RunnableConfig(configurable={}),
        )
        assert "README.md" in output
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_find_files_in_project_mode(project_workspace):
    workspace, project_path = project_workspace
    token = _set_ctx(project_path)
    try:
        result = await find_files.ainvoke(
            {"pattern": "main.py", "path": "."},
            config=RunnableConfig(configurable={}),
        )
        assert "main.py" in result
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_delete_file_in_project_mode(project_workspace):
    workspace, project_path = project_workspace
    token = _set_ctx(project_path)
    try:
        await delete_file.ainvoke(
            {"path": "main.py", "confirm": True},
            config=RunnableConfig(configurable={}),
        )
        assert not os.path.exists(os.path.join(project_path, "main.py"))
    finally:
        ContextManager.reset(token)


@pytest.mark.asyncio
async def test_move_file_in_project_mode(project_workspace):
    workspace, project_path = project_workspace
    token = _set_ctx(project_path)
    try:
        await move_file.ainvoke(
            {"source": "README.md", "destination": "README2.md"},
            config=RunnableConfig(configurable={}),
        )
        assert os.path.exists(os.path.join(project_path, "README2.md"))
        assert not os.path.exists(os.path.join(project_path, "README.md"))
    finally:
        ContextManager.reset(token)
