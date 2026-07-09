import os
import subprocess
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.core.engine.tasks import git_harvest_task


def test_git_harvest_task_logic(tmp_path):
    """
    Tests the logic flow of git_harvest_task to ensure sequential execution
    of git diff and extraction.
    """
    cwd = str(tmp_path)
    project_id = 1

    subprocess.run(["git", "init"], cwd=cwd, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=cwd, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=cwd, capture_output=True)
    test_file = tmp_path / "file.py"
    test_file.write_text("original")
    subprocess.run(["git", "add", "-A"], cwd=cwd, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=cwd, capture_output=True)
    test_file.write_text("original\nnew code")

    with patch("app.infrastructure.config.service.SystemConfigService") as mock_config, \
         patch("app.utils.template.render_template") as mock_render, \
         patch("app.core.memory.lifespan.MemoryLifespanManager") as mock_memory_container, \
         patch("app.infrastructure.llm.InternalLLMService.invoke_structured", new_callable=AsyncMock) as mock_llm:

        mock_config.get_language_preference.return_value = "en"
        mock_config.get_value.return_value = "gpt-4o"
        mock_render.return_value = "Mock Prompt"

        mock_container = MagicMock()
        mock_container.memory_manager = AsyncMock()
        mock_memory_container.is_initialized.return_value = True
        mock_memory_container.get_container.return_value = mock_container

        from app.models.schemas.git import GitConceptExtractionResult
        mock_result = GitConceptExtractionResult(
            concepts=[{"name": "Concept1", "description": "Desc1", "related_files": ["f1.py"]}]
        )
        mock_llm.return_value = mock_result

        wrapper = git_harvest_task.func
        original_func = None
        for cell in wrapper.__closure__:
            val = cell.cell_contents
            if callable(val) and getattr(val, '__name__', None) == 'git_harvest_task':
                original_func = val
                break
        assert original_func is not None
        import asyncio
        asyncio.run(original_func(cwd, project_id))

        mock_llm.assert_awaited_once()


def test_git_harvest_task_no_diff(tmp_path):
    """Verify early return when no diff exists."""
    cwd = str(tmp_path)
    project_id = 1

    subprocess.run(["git", "init"], cwd=cwd, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=cwd, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=cwd, capture_output=True)
    test_file = tmp_path / "file.py"
    test_file.write_text("original")
    subprocess.run(["git", "add", "-A"], cwd=cwd, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=cwd, capture_output=True)

    with patch("app.infrastructure.config.service.SystemConfigService") as mock_config, \
         patch("app.utils.template.render_template") as mock_render, \
         patch("app.core.memory.lifespan.MemoryLifespanManager") as mock_memory_container, \
         patch("app.infrastructure.llm.InternalLLMService.invoke_structured", new_callable=AsyncMock) as mock_llm:

        wrapper = git_harvest_task.func
        original_func = None
        for cell in wrapper.__closure__:
            val = cell.cell_contents
            if callable(val) and getattr(val, '__name__', None) == 'git_harvest_task':
                original_func = val
                break
        assert original_func is not None
        import asyncio
        asyncio.run(original_func(cwd, project_id))

        mock_llm.assert_not_awaited()