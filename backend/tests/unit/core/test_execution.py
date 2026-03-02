"""
Unit tests for Execution Module - Sandbox and Terminal execution.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
import os
import shutil

from app.core.execution import (
    Sandbox,
    LocalSandbox,
    SandboxFactory,
    TerminalManager,
    terminal_manager,
)
from app.core.execution.terminal.manager import TerminalSession


class TestTerminalSession:
    """Tests for TerminalSession dataclass."""

    def test_default_creation(self):
        """Test creating a terminal session with defaults."""
        session = TerminalSession(cwd="/tmp")

        assert session.cwd == "/tmp"
        assert "TERM" in session.env
        assert session.env["TERM"] == "xterm-256color"

    def test_custom_env(self):
        """Test creating session with custom environment."""
        custom_env = {"PATH": "/usr/bin", "CUSTOM": "value"}
        session = TerminalSession(cwd="/home", env=custom_env)

        assert session.cwd == "/home"
        assert session.env["PATH"] == "/usr/bin"
        assert session.env["CUSTOM"] == "value"
        # Note: __post_init__ adds TERM if missing
        assert "TERM" in session.env  # TERM is added by __post_init__

    def test_env_inheritance(self):
        """Test that env inherits from os.environ."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            session = TerminalSession(cwd="/tmp")
            assert session.env.get("TEST_VAR") == "test_value"


class TestTerminalManager:
    """Tests for TerminalManager."""

    def setup_method(self):
        """Clear sessions before each test."""
        TerminalManager._sessions.clear()

    def teardown_method(self):
        """Clear sessions after each test."""
        TerminalManager._sessions.clear()

    def test_get_session_new(self):
        """Test getting a new session."""
        from app.core.context import ContextManager, EvoContext

        ctx = EvoContext(thread_id="test-thread")
        token = ContextManager.set(ctx)

        try:
            session = TerminalManager.get_session()

            assert session is not None
            assert session.cwd == os.getcwd()  # Default to current working dir
        finally:
            ContextManager.reset(token)

    def test_get_session_existing(self):
        """Test getting existing session."""
        from app.core.context import ContextManager, EvoContext

        ctx = EvoContext(thread_id="test-thread")
        token = ContextManager.set(ctx)

        try:
            session1 = TerminalManager.get_session()
            session1.cwd = "/custom/path"

            session2 = TerminalManager.get_session()

            assert session1 is session2
            assert session2.cwd == "/custom/path"
        finally:
            ContextManager.reset(token)

    def test_get_session_with_working_directory(self):
        """Test session uses context working directory."""
        from app.core.context import ContextManager, EvoContext

        ctx = EvoContext(thread_id="test-thread", working_directory="/project")
        token = ContextManager.set(ctx)

        try:
            session = TerminalManager.get_session()

            assert session.cwd == "/project"
        finally:
            ContextManager.reset(token)

    def test_get_session_key_thread_id(self):
        """Test session key uses thread_id."""
        from app.core.context import ContextManager, EvoContext

        ctx = EvoContext(thread_id="thread-123", request_id="req-456")
        token = ContextManager.set(ctx)

        try:
            key = TerminalManager._get_session_key()
            assert key == "thread-123"
        finally:
            ContextManager.reset(token)

    def test_get_session_key_fallback_to_request_id(self):
        """Test session key falls back to request_id."""
        from app.core.context import ContextManager, EvoContext

        ctx = EvoContext(thread_id=None, request_id="req-456")
        token = ContextManager.set(ctx)

        try:
            key = TerminalManager._get_session_key()
            assert key == "req-456"
        finally:
            ContextManager.reset(token)

    def test_get_session_key_global_fallback(self):
        """Test session key falls back to global."""
        from app.core.context import ContextManager, EvoContext

        ctx = EvoContext(thread_id=None, request_id=None)
        token = ContextManager.set(ctx)

        try:
            key = TerminalManager._get_session_key()
            assert key == "global"
        finally:
            ContextManager.reset(token)

    @patch("app.core.execution.terminal.manager.run_command")
    def test_run_command_success(self, mock_run_command):
        """Test running a command successfully."""
        from app.core.context import ContextManager, EvoContext

        mock_result = MagicMock()
        mock_result.stdout = "output line"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        ctx = EvoContext(thread_id="test-thread")
        token = ContextManager.set(ctx)

        try:
            stdout, stderr, code = TerminalManager.run_command("ls -la")

            assert stdout == "output line"
            assert stderr == ""
            assert code == 0
            mock_run_command.assert_called_once()
        finally:
            ContextManager.reset(token)

    @patch("app.core.execution.terminal.manager.run_command")
    def test_run_command_with_error(self, mock_run_command):
        """Test running a command that returns error."""
        from app.core.context import ContextManager, EvoContext

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "error message"
        mock_result.returncode = 1
        mock_run_command.return_value = mock_result

        ctx = EvoContext(thread_id="test-thread")
        token = ContextManager.set(ctx)

        try:
            stdout, stderr, code = TerminalManager.run_command("invalid_cmd")

            assert stdout == ""
            assert stderr == "error message"
            assert code == 1
        finally:
            ContextManager.reset(token)

    def test_run_command_cd_absolute(self):
        """Test cd command with absolute path."""
        from app.core.context import ContextManager, EvoContext

        ctx = EvoContext(thread_id="test-thread")
        token = ContextManager.set(ctx)

        try:
            session = TerminalManager.get_session()
            session.cwd = "/initial"

            stdout, stderr, code = TerminalManager.run_command("cd /usr")

            assert code == 0
            assert session.cwd == "/usr"
            assert "Changed directory to" in stdout
        finally:
            ContextManager.reset(token)

    def test_run_command_cd_relative(self):
        """Test cd command with relative path."""
        from app.core.context import ContextManager, EvoContext
        import tempfile

        ctx = EvoContext(thread_id="test-thread")
        token = ContextManager.set(ctx)

        try:
            session = TerminalManager.get_session()
            # Create a temporary directory structure
            with tempfile.TemporaryDirectory() as tmpdir:
                subdir = os.path.join(tmpdir, "subdir")
                os.makedirs(subdir)
                session.cwd = tmpdir

                stdout, stderr, code = TerminalManager.run_command("cd subdir")

                assert code == 0
                assert session.cwd == subdir
        finally:
            ContextManager.reset(token)

    def test_run_command_cd_home(self):
        """Test cd command with ~ expansion."""
        from app.core.context import ContextManager, EvoContext

        ctx = EvoContext(thread_id="test-thread")
        token = ContextManager.set(ctx)

        try:
            session = TerminalManager.get_session()

            stdout, stderr, code = TerminalManager.run_command("cd ~")

            assert code == 0
            assert session.cwd == os.path.expanduser("~")
        finally:
            ContextManager.reset(token)

    def test_run_command_cd_invalid(self):
        """Test cd command with invalid directory."""
        from app.core.context import ContextManager, EvoContext

        ctx = EvoContext(thread_id="test-thread")
        token = ContextManager.set(ctx)

        try:
            session = TerminalManager.get_session()

            stdout, stderr, code = TerminalManager.run_command("cd /nonexistent_path_xyz")

            assert code == 1
            assert "no such file or directory" in stderr.lower()
        finally:
            ContextManager.reset(token)

    def test_run_command_export(self):
        """Test export command."""
        from app.core.context import ContextManager, EvoContext

        ctx = EvoContext(thread_id="test-thread")
        token = ContextManager.set(ctx)

        try:
            stdout, stderr, code = TerminalManager.run_command('export MY_VAR=my_value')

            assert code == 0
            session = TerminalManager.get_session()
            assert session.env.get("MY_VAR") == "my_value"
            assert "Exported MY_VAR" in stdout
        finally:
            ContextManager.reset(token)

    def test_run_command_export_quoted(self):
        """Test export command with quoted value."""
        from app.core.context import ContextManager, EvoContext

        ctx = EvoContext(thread_id="test-thread")
        token = ContextManager.set(ctx)

        try:
            stdout, stderr, code = TerminalManager.run_command('export PATH="/usr/local/bin"')

            assert code == 0
            session = TerminalManager.get_session()
            assert session.env.get("PATH") == "/usr/local/bin"
        finally:
            ContextManager.reset(token)

    def test_run_command_export_invalid(self):
        """Test export command with invalid format."""
        from app.core.context import ContextManager, EvoContext

        ctx = EvoContext(thread_id="test-thread")
        token = ContextManager.set(ctx)

        try:
            stdout, stderr, code = TerminalManager.run_command('export INVALID_NO_EQUALS')

            assert code == 1
            assert "invalid format" in stderr
        finally:
            ContextManager.reset(token)

    @patch("app.core.execution.terminal.manager.run_command")
    def test_run_command_exception(self, mock_run_command):
        """Test handling exception during command execution."""
        from app.core.context import ContextManager, EvoContext

        mock_run_command.side_effect = Exception("Command failed")

        ctx = EvoContext(thread_id="test-thread")
        token = ContextManager.set(ctx)

        try:
            stdout, stderr, code = TerminalManager.run_command("some_command")

            assert stdout == ""
            assert "Command failed" in stderr
            assert code == 1
        finally:
            ContextManager.reset(token)


class TestLocalSandbox:
    """Tests for LocalSandbox."""

    def test_is_sandbox_subclass(self):
        """Test LocalSandbox is a Sandbox."""
        from app.core.execution.sandbox.base import Sandbox
        assert issubclass(LocalSandbox, Sandbox)

    @patch("app.core.execution.terminal.manager.run_command")
    def test_run_command(self, mock_run_command):
        """Test running command in local sandbox."""
        mock_result = MagicMock()
        mock_result.stdout = "sandbox output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        sandbox = LocalSandbox()
        stdout, stderr, code = sandbox.run_command("echo test", timeout=30)

        assert stdout == "sandbox output"
        assert code == 0

    @patch("shutil.copy2")
    def test_upload_file_same_path(self, mock_copy2):
        """Test upload when paths are same."""
        sandbox = LocalSandbox()
        sandbox.upload_file("/same/path", "/same/path")

        mock_copy2.assert_not_called()

    @patch("shutil.copy2")
    def test_upload_file_different_path(self, mock_copy2):
        """Test upload when paths differ."""
        sandbox = LocalSandbox()
        sandbox.upload_file("/local/file", "/remote/file")

        mock_copy2.assert_called_once_with("/local/file", "/remote/file")

    @patch("shutil.copy2")
    def test_upload_file_error(self, mock_copy2):
        """Test upload file error handling."""
        mock_copy2.side_effect = PermissionError("Access denied")

        sandbox = LocalSandbox()
        with pytest.raises(PermissionError):
            sandbox.upload_file("/src", "/dst")

    @patch("shutil.copy2")
    def test_download_file_same_path(self, mock_copy2):
        """Test download when paths are same."""
        sandbox = LocalSandbox()
        sandbox.download_file("/same/path", "/same/path")

        mock_copy2.assert_not_called()

    @patch("shutil.copy2")
    def test_download_file_different_path(self, mock_copy2):
        """Test download when paths differ."""
        sandbox = LocalSandbox()
        sandbox.download_file("/remote/file", "/local/file")

        mock_copy2.assert_called_once_with("/remote/file", "/local/file")

    def test_teardown(self):
        """Test teardown does nothing for local sandbox."""
        sandbox = LocalSandbox()
        sandbox.teardown()  # Should not raise


class TestSandboxFactory:
    """Tests for SandboxFactory."""

    def setup_method(self):
        """Reset factory before each test."""
        SandboxFactory.reset()

    def teardown_method(self):
        """Reset factory after each test."""
        SandboxFactory.reset()

    @patch("app.core.execution.sandbox.factory.settings")
    def test_get_sandbox_local_mode(self, mock_settings):
        """Test getting sandbox in local mode."""
        mock_settings.EXECUTION_MODE = "local"

        sandbox = SandboxFactory.get_sandbox()

        assert isinstance(sandbox, LocalSandbox)

    @patch("app.core.execution.sandbox.factory.settings")
    def test_get_sandbox_singleton(self, mock_settings):
        """Test sandbox is singleton."""
        mock_settings.EXECUTION_MODE = "local"

        sandbox1 = SandboxFactory.get_sandbox()
        sandbox2 = SandboxFactory.get_sandbox()

        assert sandbox1 is sandbox2

    @patch("app.core.execution.sandbox.factory.settings")
    def test_get_sandbox_docker_mode_fallback(self, mock_settings):
        """Test fallback to local when Docker fails."""
        mock_settings.EXECUTION_MODE = "docker"
        mock_settings.SANDBOX_IMAGE = "python:3.11"

        # Docker import will fail
        with patch.dict("sys.modules", {"app.core.execution.sandbox.docker": None}):
            sandbox = SandboxFactory.get_sandbox()

        assert isinstance(sandbox, LocalSandbox)

    def test_reset(self):
        """Test resetting factory."""
        from app.core.execution.sandbox.factory import SandboxFactory

        # Create a mock sandbox
        mock_sandbox = MagicMock()
        SandboxFactory._instance = mock_sandbox

        SandboxFactory.reset()

        mock_sandbox.teardown.assert_called_once()
        assert SandboxFactory._instance is None

    def test_reset_none_instance(self):
        """Test resetting when instance is None."""
        from app.core.execution.sandbox.factory import SandboxFactory

        SandboxFactory._instance = None

        # Should not raise
        SandboxFactory.reset()


class TestGlobalInstances:
    """Tests for global instances."""

    def test_terminal_manager_is_class(self):
        """Test terminal_manager is the class itself."""
        from app.core.execution import terminal_manager

        assert terminal_manager is TerminalManager

    def test_sandbox_factory_accessible(self):
        """Test SandboxFactory is accessible."""
        from app.core.execution import SandboxFactory

        assert SandboxFactory is not None
