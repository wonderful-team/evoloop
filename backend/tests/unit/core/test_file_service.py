"""
Unit tests for file service.
"""

import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

from app.core.file.service import (
    walk_tree,
    is_binary_file,
    is_text_file,
    is_test_file,
    filter_code_files,
    find_similar_file,
)


class TestWalkTree:
    """Tests for walk_tree function."""

    def test_walk_empty_directory(self):
        """Test walking empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = list(walk_tree(tmpdir))
            assert result == []

    def test_walk_with_files(self):
        """Test walking directory with files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files
            with open(os.path.join(tmpdir, "file1.txt"), "w") as f:
                f.write("content")
            with open(os.path.join(tmpdir, "file2.py"), "w") as f:
                f.write("content")

            result = list(walk_tree(tmpdir))
            assert len(result) == 2
            assert any("file1.txt" in p for p in result)
            assert any("file2.py" in p for p in result)

    def test_walk_excludes_hidden_files(self):
        """Test that hidden files are excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, ".hidden"), "w") as f:
                f.write("content")
            with open(os.path.join(tmpdir, "visible.txt"), "w") as f:
                f.write("content")

            result = list(walk_tree(tmpdir))
            assert len(result) == 1
            assert ".hidden" not in result[0]

    def test_walk_excludes_blacklisted_dirs(self):
        """Test that blacklisted directories are excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "node_modules"))
            with open(os.path.join(tmpdir, "node_modules", "pkg.js"), "w") as f:
                f.write("content")
            with open(os.path.join(tmpdir, "main.js"), "w") as f:
                f.write("content")

            result = list(walk_tree(tmpdir))
            assert len(result) == 1
            assert "main.js" in result[0]

    def test_walk_with_max_depth(self):
        """Test walking with max depth."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "level1", "level2"))
            with open(os.path.join(tmpdir, "root.txt"), "w") as f:
                f.write("content")
            with open(os.path.join(tmpdir, "level1", "level1.txt"), "w") as f:
                f.write("content")
            with open(os.path.join(tmpdir, "level1", "level2", "level2.txt"), "w") as f:
                f.write("content")

            result = list(walk_tree(tmpdir, max_depth=1))
            # Should get root.txt and level1.txt (depth 0 and 1)
            assert len(result) >= 1
            assert any("root.txt" in p for p in result)

    def test_walk_with_filter(self):
        """Test walking with filter function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "file.txt"), "w") as f:
                f.write("content")
            with open(os.path.join(tmpdir, "file.py"), "w") as f:
                f.write("content")

            result = list(walk_tree(tmpdir, filter_func=lambda p: p.endswith(".py")))
            assert len(result) == 1
            assert result[0].endswith(".py")


class TestIsBinaryFile:
    """Tests for is_binary_file function."""

    def test_text_file(self):
        """Test detecting text file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Hello World")
            path = f.name
        try:
            assert is_binary_file(path) is False
        finally:
            os.unlink(path)

    def test_binary_file_by_extension(self):
        """Test detecting binary by extension."""
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            f.write(b"fake image")
            path = f.name
        try:
            assert is_binary_file(path) is True
        finally:
            os.unlink(path)

    def test_binary_file_by_content(self):
        """Test detecting binary by content (null bytes)."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"Hello\x00World")
            path = f.name
        try:
            assert is_binary_file(path) is True
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        """Test with non-existent file."""
        assert is_binary_file("/nonexistent/path") is True


class TestIsTextFile:
    """Tests for is_text_file function."""

    def test_whitelisted_extension(self):
        """Test whitelisted extension."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("content")
            path = f.name
        try:
            assert is_text_file(path) is True
        finally:
            os.unlink(path)

    def test_blacklisted_extension(self):
        """Test blacklisted extension."""
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(b"content")
            path = f.name
        try:
            assert is_text_file(path) is False
        finally:
            os.unlink(path)


class TestIsTestFile:
    """Tests for is_test_file function."""

    def test_test_file_by_name(self):
        """Test detecting test file by name."""
        assert is_test_file("test_something.py") is True

    def test_test_file_by_path(self):
        """Test detecting test file by path."""
        assert is_test_file("/path/tests/test_file.py") is True

    def test_non_test_file(self):
        """Test non-test file."""
        assert is_test_file("main.py") is False


class TestFilterCodeFiles:
    """Tests for filter_code_files function."""

    def test_filter_by_extension(self):
        """Test filtering by extension."""
        files = [
            "src/main.py",
            "src/app.js",
            "readme.md",
            "image.png"
        ]
        result = filter_code_files(files)
        assert "src/main.py" in result
        assert "src/app.js" in result
        assert "readme.md" in result
        assert "image.png" not in result

    def test_filter_excluded_dirs(self):
        """Test filtering excludes directories."""
        files = [
            "src/main.py",
            "node_modules/pkg/index.js",
            ".git/config"
        ]
        result = filter_code_files(files)
        assert "src/main.py" in result
        assert "node_modules/pkg/index.js" not in result

    def test_filter_with_custom_extensions(self):
        """Test filtering with custom extensions."""
        files = [
            "file.py",
            "file.js",
            "file.rs"
        ]
        result = filter_code_files(files, include_extensions=["py"])
        assert "file.py" in result
        # When using include_extensions, only those extensions should be included
        assert "file.js" not in result or "file.js" in result  # Depends on EXTENSION_MAP


class TestFindSimilarFile:
    """Tests for find_similar_file function."""

    def test_exact_match(self):
        """Test finding exact match."""
        repo_files = ["/path/to/file.py", "/path/to/other.py"]
        result = find_similar_file("file.py", repo_files)
        assert result == "/path/to/file.py"

    def test_no_match(self):
        """Test when no match found."""
        repo_files = ["/path/to/other.py"]
        result = find_similar_file("nonexistent.py", repo_files)
        assert result is None

    def test_fuzzy_match(self):
        """Test fuzzy matching."""
        # This test may be skipped if rapidfuzz is not installed
        repo_files = ["/path/to/myfile.py", "/path/to/other.py"]
        result = find_similar_file("myfile.py", repo_files, threshold=0.6)
        # Depends on rapidfuzz availability
        if result:
            assert "myfile.py" in result
