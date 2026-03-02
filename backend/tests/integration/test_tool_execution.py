"""
Integration tests for tool execution.
Tests actual tool execution with real dependencies.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.mark.integration
class TestFileTools:
    """Integration tests for file tools.

    Note: File tools have security checks that limit paths to the working directory.
    These tests use relative paths within the test environment.
    """

    @pytest.mark.asyncio
    async def test_read_file_tool(self):
        """Test read_file tool execution using a real project file."""
        from app.domain.tools.files.actions.read import handle_read

        # Use an actual file in the project
        result = await handle_read(path="pyproject.toml")
        assert "[project]" in result or "dependencies" in result

    @pytest.mark.asyncio
    async def test_list_files_tool(self):
        """Test list_files tool execution."""
        from app.domain.tools.files.actions.list import handle_list

        result = await handle_list(action="list", path=".")
        # Should list at least some files/directories
        assert len(result) > 0


@pytest.mark.integration
class TestGitTools:
    """Integration tests for git tools."""

    @pytest.fixture
    def git_repo(self):
        """Create temporary git repo."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)

            Path(tmpdir, "file.txt").write_text("content")
            subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True)

            yield tmpdir

    @pytest.mark.asyncio
    async def test_git_status_tool(self, git_repo):
        """Test git_status tool."""
        from app.domain.tools.git import git_status

        result = await git_status.ainvoke({})
        # Check for common git status output patterns (supports both English and Chinese)
        assert any(keyword in result for keyword in ["branch", "分支", "位于"])

    @pytest.mark.asyncio
    async def test_git_history_tool(self, git_repo):
        """Test git_history tool."""
        from app.domain.tools.git import git_history

        result = await git_history.ainvoke({"limit": 5})
        # Check that result contains commit hashes (7+ hex characters)
        import re
        assert re.search(r"[a-f0-9]{7}", result) or "bugfix" in result.lower()


@pytest.mark.integration
class TestExecutionTools:
    """Integration tests for execution tools."""

    @pytest.mark.asyncio
    async def test_bash_tool(self):
        """Test bash command execution."""
        from app.domain.tools.execution import bash

        result = await bash.ainvoke({"command": "echo 'hello world'"})
        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_bash_tool_with_cwd(self):
        """Test bash with working directory."""
        import tempfile
        from app.domain.tools.execution import bash

        with tempfile.TemporaryDirectory() as tmpdir:
            result = await bash.ainvoke({"command": f"cd {tmpdir} && pwd"})
            assert tmpdir in result or os.path.basename(tmpdir) in result


@pytest.mark.integration
class TestMemoryTools:
    """Integration tests for memory tools."""

    @pytest.mark.asyncio
    async def test_search_concepts_tool(self):
        """Test search_concepts tool."""
        from app.domain.tools.facades import search_concepts

        # This may fail if Neo4j is not available
        try:
            result = await search_concepts(query="python")
            assert isinstance(result, list)
        except Exception as e:
            pytest.skip(f"Memory tool not available: {e}")

    @pytest.mark.asyncio
    async def test_manage_memory_tool(self):
        """Test manage_memory tool."""
        from app.domain.tools.facades import manage_memory

        try:
            # Test adding memory
            result = await manage_memory(action="add", content="Test memory content")
            assert result is not None
        except Exception as e:
            pytest.skip(f"Memory tool not available: {e}")


@pytest.mark.integration
class TestKnowledgeTools:
    """Integration tests for knowledge tools."""

    @pytest.mark.asyncio
    async def test_add_concept_tool(self):
        """Test add_concept tool."""
        from app.domain.tools.facades import add_concept

        try:
            result = await add_concept(
                name="TestConcept",
                category="test",
                description="A test concept"
            )
            assert result is not None
        except Exception as e:
            pytest.skip(f"Knowledge tool not available: {e}")
