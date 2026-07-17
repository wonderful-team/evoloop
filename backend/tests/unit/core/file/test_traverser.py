"""Unit tests for app.core.file.traverser."""

import tempfile
from pathlib import Path

import pytest

from app.core.file.traverser import FileTraverser, TraverseOptions


class TestFileTraverserGitignore:
    """Tests for .gitignore integration in FileTraverser."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repository with a .gitignore file."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text(
                "node_modules/\n*.log\nignored_dir/\n", encoding="utf-8"
            )
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "pkg.js").write_text("module", encoding="utf-8")
            (root / "debug.log").write_text("log", encoding="utf-8")
            (root / "ignored_dir").mkdir()
            (root / "ignored_dir" / "secret.txt").write_text("secret", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "inner.txt").write_text("nested", encoding="utf-8")
            yield root

    def test_walk_auto_detects_gitignore(self, temp_repo):
        """walk() should auto-detect .gitignore in root and skip ignored entries."""
        files = list(FileTraverser.walk(str(temp_repo)))
        assert (temp_repo / "src" / "main.py") in [Path(p) for p in files]
        assert (temp_repo / "node_modules" / "pkg.js") not in [Path(p) for p in files]
        assert (temp_repo / "debug.log") not in [Path(p) for p in files]
        assert (temp_repo / "ignored_dir" / "secret.txt") not in [Path(p) for p in files]
        assert (temp_repo / "nested" / "inner.txt") in [Path(p) for p in files]

    def test_walk_explicit_gitignore_root(self, temp_repo):
        """walk() should respect explicitly provided gitignore_root."""
        # Pass a different directory without .gitignore to disable gitignore filtering
        with tempfile.TemporaryDirectory() as other:
            files = list(
                FileTraverser.walk(
                    str(temp_repo),
                    TraverseOptions(gitignore_root=other),
                )
            )
            paths = [Path(p) for p in files]
            # node_modules is still excluded by DEFAULT_EXCLUDED_DIRS regardless of gitignore
            assert (temp_repo / "node_modules" / "pkg.js") not in paths
            # debug.log and ignored_dir should now appear because gitignore is disabled
            assert (temp_repo / "debug.log") in paths
            assert (temp_repo / "ignored_dir" / "secret.txt") in paths

    def test_list_entries_respects_gitignore(self, temp_repo):
        """list_entries() should skip .gitignore entries."""
        entries = list(FileTraverser.list_entries(str(temp_repo)))
        names = {e.name for e in entries}
        assert "node_modules" not in names
        assert "debug.log" not in names
        assert "ignored_dir" not in names
        assert "src" in names
        assert "nested" in names

    def test_list_entries_without_gitignore(self, temp_repo):
        """list_entries() with explicit empty gitignore_root should include ignored entries."""
        with tempfile.TemporaryDirectory() as other:
            entries = list(FileTraverser.list_entries(str(temp_repo), gitignore_root=other))
            names = {e.name for e in entries}
            # node_modules is still excluded by DEFAULT_EXCLUDED_DIRS
            assert "node_modules" not in names
            assert "debug.log" in names
            assert "ignored_dir" in names

    def test_walk_auto_detects_gitignore_in_parent(self):
        """walk() should auto-detect .gitignore in a parent directory."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("*.log\n", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "src").mkdir()
            (root / "sub" / "src" / "main.py").write_text("code", encoding="utf-8")
            (root / "sub" / "trace.log").write_text("log", encoding="utf-8")
            # Walk from sub/ — no .gitignore here, but parent has one
            files = list(FileTraverser.walk(str(root / "sub")))
            paths = [Path(p) for p in files]
            assert (root / "sub" / "src" / "main.py") in paths
            assert (root / "sub" / "trace.log") not in paths
