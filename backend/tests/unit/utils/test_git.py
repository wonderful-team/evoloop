"""
Unit tests for git utilities.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.utils.git import git_command, get_current_branch, get_git_root, is_git_repo


class TestGitCommand:
    """Tests for git_command function."""

    def test_git_command_success(self):
        """Test successful git command execution."""
        with patch('app.utils.git.run_command') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="output",
                stderr="",
                success=True
            )

            result = git_command(["status"])

            assert result.success is True
            assert result.stdout == "output"
            mock_run.assert_called_once_with(["git", "status"], cwd=None, check=False)

    def test_git_command_with_cwd(self):
        """Test git command with working directory."""
        with patch('app.utils.git.run_command') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="output",
                stderr="",
                success=True
            )

            result = git_command(["log"], cwd="/project")

            mock_run.assert_called_once_with(["git", "log"], cwd="/project", check=False)

    def test_git_command_failure(self):
        """Test failed git command."""
        with patch('app.utils.git.run_command') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error",
                success=False
            )

            result = git_command(["invalid-command"])

            assert result.success is False
            assert result.returncode == 1


class TestGetCurrentBranch:
    """Tests for get_current_branch function."""

    def test_get_current_branch_success(self):
        """Test getting current branch successfully."""
        with patch('app.utils.git.git_command') as mock_git:
            mock_git.return_value = MagicMock(
                returncode=0,
                stdout="main\n",
                success=True
            )

            result = get_current_branch()

            assert result == "main"
            mock_git.assert_called_once_with(["rev-parse", "--abbrev-ref", "HEAD"], cwd=None)

    def test_get_current_branch_failure(self):
        """Test getting current branch when not in a git repo."""
        with patch('app.utils.git.git_command') as mock_git:
            mock_git.return_value = MagicMock(
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository",
                success=False
            )

            result = get_current_branch()

            assert result == ""


class TestGetGitRoot:
    """Tests for get_git_root function."""

    def test_get_git_root_success(self):
        """Test getting git root successfully."""
        with patch('app.utils.git.git_command') as mock_git:
            mock_git.return_value = MagicMock(
                returncode=0,
                stdout="/home/user/project\n",
                success=True
            )

            result = get_git_root()

            assert result == "/home/user/project"
            mock_git.assert_called_once_with(["rev-parse", "--show-toplevel"], cwd=None)

    def test_get_git_root_failure(self):
        """Test getting git root when not in a git repo."""
        with patch('app.utils.git.git_command') as mock_git:
            mock_git.return_value = MagicMock(
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository",
                success=False
            )

            result = get_git_root()

            assert result == ""


class TestIsGitRepo:
    """Tests for is_git_repo function."""

    def test_is_git_repo_true(self):
        """Test checking if directory is a git repo (true)."""
        with patch('app.utils.git.git_command') as mock_git:
            mock_git.return_value = MagicMock(
                returncode=0,
                stdout="true\n",
                success=True
            )

            result = is_git_repo()

            assert result is True
            mock_git.assert_called_once_with(["rev-parse", "--is-inside-work-tree"], cwd=None)

    def test_is_git_repo_false(self):
        """Test checking if directory is a git repo (false)."""
        with patch('app.utils.git.git_command') as mock_git:
            mock_git.return_value = MagicMock(
                returncode=0,
                stdout="false\n",
                success=True
            )

            result = is_git_repo()

            assert result is False

    def test_is_git_repo_failure(self):
        """Test checking if directory is a git repo (command fails)."""
        with patch('app.utils.git.git_command') as mock_git:
            mock_git.return_value = MagicMock(
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository",
                success=False
            )

            result = is_git_repo()

            assert result is False
