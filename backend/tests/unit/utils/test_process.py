"""
Unit tests for process utilities.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import subprocess

from app.utils.process import CommandResult, run_command, run_async_command


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_success_property_true(self):
        """Test success property when returncode is 0."""
        result = CommandResult(returncode=0, stdout="output", stderr="")
        assert result.success is True

    def test_success_property_false(self):
        """Test success property when returncode is non-zero."""
        result = CommandResult(returncode=1, stdout="", stderr="error")
        assert result.success is False

    def test_output_property(self):
        """Test output property returns stripped stdout."""
        result = CommandResult(returncode=0, stdout="  output with spaces  ", stderr="")
        assert result.output == "output with spaces"


class TestRunCommand:
    """Tests for run_command function."""

    def test_run_command_with_list(self):
        """Test running command with list arguments."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="output",
                stderr=""
            )

            result = run_command(["ls", "-la"])

            assert result.success is True
            assert result.stdout == "output"
            mock_run.assert_called_once()
            # Check shell=False for list input
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['shell'] is False

    def test_run_command_with_string(self):
        """Test running command with string arguments."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="output",
                stderr=""
            )

            result = run_command("ls -la")

            assert result.success is True
            mock_run.assert_called_once()
            # Check shell=True for string input
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['shell'] is True

    def test_run_command_with_cwd(self):
        """Test running command with working directory."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="output",
                stderr=""
            )

            result = run_command(["ls"], cwd="/tmp")

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['cwd'] == "/tmp"

    def test_run_command_with_env(self):
        """Test running command with environment variables."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="output",
                stderr=""
            )

            env = {"VAR": "value"}
            result = run_command(["echo", "$VAR"], env=env)

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['env'] == env

    def test_run_command_failure(self):
        """Test running command that fails."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error message"
            )

            result = run_command(["false"])

            assert result.success is False
            assert result.returncode == 1
            assert result.stderr == "error message"

    def test_run_command_exception(self):
        """Test running command that raises exception."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Command not found")

            result = run_command(["nonexistent"])

            assert result.returncode == -1
            assert "Command not found" in result.stderr

    def test_run_command_with_timeout(self):
        """Test running command with timeout."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="output",
                stderr=""
            )

            result = run_command(["sleep", "1"], timeout=5.0)

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['timeout'] == 5.0


class TestRunAsyncCommand:
    """Tests for run_async_command function."""

    @pytest.mark.asyncio
    async def test_run_async_command_with_list(self):
        """Test running async command with list arguments."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(
            b"output",
            b""
        ))

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            result = await run_async_command(["ls", "-la"])

            assert result.success is True
            assert result.stdout == "output"

    @pytest.mark.asyncio
    async def test_run_async_command_with_string(self):
        """Test running async command with string arguments."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(
            b"output",
            b""
        ))

        with patch('asyncio.create_subprocess_shell', return_value=mock_process):
            result = await run_async_command("ls -la")

            assert result.success is True
            assert result.stdout == "output"

    @pytest.mark.asyncio
    async def test_run_async_command_with_timeout(self):
        """Test running async command with timeout."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = MagicMock(return_value=(b"output", b""))
        mock_process.kill = MagicMock()

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            with patch('asyncio.wait_for') as mock_wait_for:
                mock_wait_for.return_value = (b"output", b"")

                result = await run_async_command(["ls"], timeout=5.0)

                assert result.success is True

    @pytest.mark.asyncio
    async def test_run_async_command_timeout_error(self):
        """Test running async command that times out."""
        mock_process = MagicMock()
        mock_process.kill = MagicMock()

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            with patch('asyncio.wait_for') as mock_wait_for:
                mock_wait_for.side_effect = TimeoutError()

                result = await run_async_command(["sleep", "10"], timeout=1.0)

                assert result.returncode == -1
                assert "timed out" in result.stderr.lower()
                mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_async_command_exception(self):
        """Test running async command that raises exception."""
        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_exec.side_effect = Exception("Failed to create process")

            result = await run_async_command(["ls"])

            assert result.returncode == -1
            assert "Failed to create process" in result.stderr
