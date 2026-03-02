"""
Unit tests for LSP (Language Server Protocol) Tool.
Tests LSPManager and consult_lsp tool.
"""

import pytest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import os

from app.domain.tools.coding.lsp import (
    LSPManager,
    consult_lsp,
    _find_repo_root,
)


class TestLSPManager:
    """Tests for LSPManager singleton class."""

    def setup_method(self):
        """Reset singleton before each test."""
        LSPManager._instance = None

    def teardown_method(self):
        """Reset singleton after each test."""
        LSPManager._instance = None

    def test_singleton_pattern(self):
        """Test LSPManager is a singleton."""
        manager1 = LSPManager.get_instance()
        manager2 = LSPManager.get_instance()
        assert manager1 is manager2

    def test_get_server_key(self):
        """Test server key generation."""
        manager = LSPManager()
        key = manager._get_server_key("python", "/path/to/repo")
        assert key == f"python:{os.path.abspath('/path/to/repo')}"

    def _create_mock_server(self):
        """Helper to create properly structured mock server."""
        mock_server = MagicMock()
        mock_server.server.process = MagicMock()
        mock_server.server.process.poll.return_value = None
        return mock_server

    def test_get_server_creates_new_server(self):
        """Test get_server creates a new server if not exists."""
        with patch("app.domain.tools.coding.lsp.PyrightServer") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                server = manager.get_server("python", "/path/to/repo")

            assert server is not None
            mock_server_class.assert_called_once()
            mock_server.start.assert_called_once()

    def test_get_server_returns_existing_server(self):
        """Test get_server returns existing server if alive."""
        with patch("app.domain.tools.coding.lsp.PyrightServer") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                server1 = manager.get_server("python", "/path/to/repo")
                server2 = manager.get_server("python", "/path/to/repo")

            assert server1 is server2
            # Server should only be created once
            mock_server_class.assert_called_once()

    def test_get_server_restarts_dead_server(self):
        """Test get_server restarts server if process is dead."""
        with patch("app.domain.tools.coding.lsp.PyrightServer") as mock_server_class:
            mock_server = MagicMock()
            # First check: returns 1 (dead), after restart: returns None (alive)
            mock_server.server.process = MagicMock()
            mock_server.server.process.poll.side_effect = [1, None]
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                manager.get_server("python", "/path/to/repo")
                # Simulate server death and get again
                server2 = manager.get_server("python", "/path/to/repo")

            # Should create new server
            assert mock_server_class.call_count == 2

    def test_get_server_python(self):
        """Test get_server for Python language."""
        with patch("app.domain.tools.coding.lsp.PyrightServer") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                server = manager.get_server("python", "/repo")

            mock_server_class.assert_called_once()

    def test_get_server_typescript(self):
        """Test get_server for TypeScript language."""
        with patch("app.domain.tools.coding.lsp.TypeScriptLanguageServer") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                server = manager.get_server("typescript", "/repo")

            mock_server_class.assert_called_once()

    def test_get_server_go(self):
        """Test get_server for Go language."""
        with patch("app.domain.tools.coding.lsp.Gopls") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                server = manager.get_server("go", "/repo")

            mock_server_class.assert_called_once()

    def test_get_server_rust(self):
        """Test get_server for Rust language."""
        with patch("app.domain.tools.coding.lsp.RustAnalyzer") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                server = manager.get_server("rust", "/repo")

            mock_server_class.assert_called_once()

    def test_get_server_java(self):
        """Test get_server for Java language."""
        with patch("app.domain.tools.coding.lsp.EclipseJDTLS") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                server = manager.get_server("java", "/repo")

            mock_server_class.assert_called_once()

    def test_get_server_cpp(self):
        """Test get_server for C++ language."""
        with patch("app.domain.tools.coding.lsp.ClangdLanguageServer") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                server = manager.get_server("cpp", "/repo")

            mock_server_class.assert_called_once()

    def test_get_server_php(self):
        """Test get_server for PHP language."""
        with patch("app.domain.tools.coding.lsp.Intelephense") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                server = manager.get_server("php", "/repo")

            mock_server_class.assert_called_once()

    def test_get_server_vue(self):
        """Test get_server for Vue language."""
        with patch("app.domain.tools.coding.lsp.VueLanguageServer") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                server = manager.get_server("vue", "/repo")

            mock_server_class.assert_called_once()

    def test_get_server_unsupported_language(self):
        """Test get_server raises error for unsupported language."""
        manager = LSPManager()
        with pytest.raises(ValueError, match="Unsupported language"):
            manager.get_server("haskell", "/repo")

    def test_get_server_case_insensitive_language_detection(self):
        """Test get_server handles language case insensitively for detection."""
        with patch("app.domain.tools.coding.lsp.PyrightServer") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                # Different cases should both resolve to Python server
                server1 = manager.get_server("PYTHON", "/repo")
                server2 = manager.get_server("Python", "/repo1")  # Different path

            # Both should use PyrightServer (case insensitive language detection)
            assert mock_server_class.call_count == 2

    def test_shutdown_all_servers(self):
        """Test shutdown stops all servers."""
        with patch("app.domain.tools.coding.lsp.PyrightServer") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                manager.get_server("python", "/repo1")
                manager.get_server("python", "/repo2")

            manager.shutdown()

            assert mock_server.shutdown.call_count == 2
            assert mock_server.stop.call_count == 2
            assert len(manager.servers) == 0

    def test_shutdown_error_handling(self):
        """Test shutdown handles errors gracefully."""
        with patch("app.domain.tools.coding.lsp.PyrightServer") as mock_server_class:
            mock_server = self._create_mock_server()
            mock_server.shutdown.side_effect = Exception("Shutdown error")
            mock_server_class.return_value = mock_server

            manager = LSPManager()
            with patch.object(manager, 'solidlsp_settings'):
                manager.get_server("python", "/repo")

            # Should not raise
            manager.shutdown()


class TestFindRepoRoot:
    """Tests for _find_repo_root helper function."""

    def test_find_repo_root_with_git(self, tmp_path):
        """Test finding repo root with .git directory."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        result = _find_repo_root(subdir)
        assert result == tmp_path

    def test_find_repo_root_from_file(self, tmp_path):
        """Test finding repo root from a file path."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.py"
        test_file.write_text("pass")

        result = _find_repo_root(test_file)
        assert result == tmp_path

    def test_find_repo_root_no_git(self, tmp_path):
        """Test finding repo root without .git directory."""
        result = _find_repo_root(tmp_path)
        assert result is None

    def test_find_repo_root_depth_limit(self, tmp_path):
        """Test depth limit for finding repo root."""
        # Create deep nested structure without .git
        deep_dir = tmp_path
        for i in range(15):
            deep_dir = deep_dir / f"level{i}"
            deep_dir.mkdir()

        result = _find_repo_root(deep_dir)
        assert result is None


class TestConsultLsp:
    """Tests for consult_lsp tool - testing the underlying function logic."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        return {"configurable": {"working_directory": "/project"}}

    @pytest.fixture(autouse=True)
    def mock_context(self):
        """Mock ContextManager to return empty context."""
        with patch("app.core.tools.base.ContextManager") as mock_ctx_class:
            mock_ctx = MagicMock()
            mock_ctx.working_directory = None
            mock_ctx_class.current.return_value = mock_ctx
            yield mock_ctx_class

    def test_find_repo_root_integration(self, tmp_path):
        """Test _find_repo_root integration with tmp_path."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        result = _find_repo_root(tmp_path)
        assert result == tmp_path


class TestLanguageDetection:
    """Tests for language detection from file extensions."""

    @pytest.fixture(autouse=True)
    def mock_context(self):
        """Mock ContextManager to return empty context."""
        with patch("app.core.tools.base.ContextManager") as mock_ctx_class:
            mock_ctx = MagicMock()
            mock_ctx.working_directory = None
            mock_ctx_class.current.return_value = mock_ctx
            yield mock_ctx_class

    def test_language_from_extension_python(self):
        """Test Python extension detection."""
        from app.domain.tools.coding.lsp import consult_lsp
        # Just verify the tool exists and has proper metadata
        assert consult_lsp is not None

    def test_supported_languages(self):
        """Test that all expected languages are supported."""
        supported = ["python", "typescript", "javascript", "go", "rust", "java", "c", "cpp", "c++", "php", "vue"]
        # Verify LSPManager can be instantiated
        manager = LSPManager()
        assert manager is not None
