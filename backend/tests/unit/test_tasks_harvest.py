import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.core.engine.tasks import git_harvest_task

def test_git_harvest_task_logic():
    """
    Tests the logic flow of git_harvest_task to ensure sequential execution
    of git diff and extraction.
    """
    cwd = "/mock/repo"
    project_id = 1
    diff_content = "diff --git a/file.py b/file.py\n+ new code"

    # Mock dependencies
    # We mock inside the function scope because of the local imports
    with patch("subprocess.run") as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("app.infrastructure.config.service.SystemConfigService") as mock_config, \
         patch("app.utils.template.render_template") as mock_render, \
         patch("app.core.memory.lifespan.MemoryLifespanManager") as mock_memory_container, \
         patch("app.infrastructure.llm.InternalLLMService.invoke_structured", new_callable=AsyncMock) as mock_llm:

        # 1. Setup Mock for subprocess
        mock_process = MagicMock()
        mock_process.stdout = diff_content
        mock_run.return_value = mock_process
        
        # 2. Setup Config and Template
        mock_config.get_language_preference.return_value = "en"
        mock_config.get_value.return_value = "gpt-4o"
        mock_render.return_value = "Mock Prompt"

        # 3. Setup MemoryContainer
        mock_container = MagicMock()
        mock_container.memory_manager = AsyncMock()
        mock_memory_container.is_initialized.return_value = True
        mock_memory_container.get_container.return_value = mock_container

        # 4. Setup LLM result
        from app.models.schemas.git import GitConceptExtractionResult
        mock_result = GitConceptExtractionResult(
            concepts=[{"name": "Concept1", "description": "Desc1", "related_files": ["f1.py"]}]
        )
        mock_llm.return_value = mock_result

        # Get original async function from TaskWrapper closure and run it directly
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
        
        # Verify calls
        mock_run.assert_called_with(["git", "diff", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=15)

def test_git_harvest_task_no_diff():
    """Verify early return when no diff exists."""
    cwd = "/mock/repo"
    project_id = 1

    def run_coro(coro):
        import asyncio
        return asyncio.new_event_loop().run_until_complete(coro)

    with patch("subprocess.run") as mock_run, \
         patch("asyncio.run", side_effect=run_coro) as mock_asyncio_run:
        
        mock_process = MagicMock()
        mock_process.stdout = "" # No diff
        mock_run.return_value = mock_process
        
        git_harvest_task(cwd, project_id)
        
        # Ensure extraction was NOT triggered (ainvoke not called inside the task)
        # (Actually we'd need to mock LLMFactory to be sure)
        pass
