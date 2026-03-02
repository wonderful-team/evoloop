"""
Unit tests for Codebase Domain Module.
Tests FileFilter, GitignoreMatcher, and core indexing/retrieval functionality.
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

from app.domain.codebase.filter import FileFilter
from app.domain.codebase.ignore import GitignoreMatcher


class TestFileFilter:
    """Tests for FileFilter."""

    @pytest.fixture
    def file_filter(self):
        return FileFilter()

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_should_include_symlink(self, file_filter):
        """Test that symlinks are excluded."""
        with patch('os.path.islink', return_value=True):
            result = file_filter.should_include("/path/to/link")

        assert result is False

    def test_should_include_hidden_file(self, file_filter):
        """Test that hidden files are excluded."""
        result = file_filter.should_include("/path/.hidden_file.py")

        assert result is False

    def test_should_include_hidden_dir(self, file_filter):
        """Test that files in hidden directories are excluded."""
        result = file_filter.should_include("/path/.git/config")

        assert result is False

    def test_should_include_excluded_dir(self, file_filter):
        """Test that files in excluded directories are filtered."""
        result = file_filter.should_include("/project/node_modules/package.json")

        assert result is False

    def test_should_include_excluded_file(self, file_filter):
        """Test that excluded file patterns are filtered."""
        result = file_filter.should_include("/project/package-lock.json")

        assert result is False

    @patch('app.domain.codebase.filter.is_text_file', return_value=True)
    @patch('app.domain.codebase.filter.is_encrypted_path', return_value=False)
    def test_should_include_text_file(self, mock_encrypted, mock_text, file_filter, temp_dir):
        """Test that text files are included."""
        test_file = os.path.join(temp_dir, "test.py")
        Path(test_file).touch()

        result = file_filter.should_include(test_file)

        assert result is True

    @patch('app.domain.codebase.filter.is_text_file', return_value=False)
    def test_should_include_non_text_file(self, mock_text, file_filter):
        """Test that non-text files are excluded."""
        result = file_filter.should_include("/path/binary.exe")

        assert result is False

    @patch('app.domain.codebase.filter.is_text_file', return_value=True)
    @patch('app.domain.codebase.filter.is_encrypted_path', return_value=True)
    def test_should_include_encrypted_file(self, mock_encrypted, mock_text, file_filter):
        """Test that encrypted files are excluded."""
        result = file_filter.should_include("/path/encrypted.txt")

        assert result is False

    def test_should_include_with_inclusion_rules(self, file_filter, temp_dir):
        """Test inclusion rules."""
        test_file = os.path.join(temp_dir, "test.py")
        Path(test_file).touch()

        inclusions = {"ext": [".py"], "file": [], "dir": []}

        with patch('app.domain.codebase.filter.is_text_file', return_value=True), \
             patch('app.domain.codebase.filter.is_encrypted_path', return_value=False):
            result = file_filter.should_include(test_file, inclusions=inclusions)

        assert result is True

    def test_should_include_with_exclusion_rules(self, file_filter, temp_dir):
        """Test exclusion rules."""
        test_file = os.path.join(temp_dir, "test.js")
        Path(test_file).touch()

        exclusions = {"ext": [".py"], "file": [], "dir": []}

        with patch('app.domain.codebase.filter.is_text_file', return_value=True), \
             patch('app.domain.codebase.filter.is_encrypted_path', return_value=False):
            result = file_filter.should_include(test_file, exclusions=exclusions)

        assert result is True  # .js not in exclusion list

    def test_cache_functionality(self, file_filter, temp_dir):
        """Test that caching works correctly."""
        test_file = os.path.join(temp_dir, "cache_test.py")
        Path(test_file).touch()

        with patch('app.domain.codebase.filter.is_text_file', return_value=True), \
             patch('app.domain.codebase.filter.is_encrypted_path', return_value=False):
            # First call
            result1 = file_filter.should_include(test_file)
            # Second call should use cache
            result2 = file_filter.should_include(test_file)

        assert result1 is True
        assert result2 is True

    def test_parse_inclusion_file(self, file_filter, temp_dir):
        """Test parsing inclusion/exclusion file."""
        config_file = os.path.join(temp_dir, "config.txt")
        with open(config_file, "w") as f:
            f.write("# This is a comment\n")
            f.write("ext:.py\n")
            f.write("file:README.md\n")
            f.write("dir:src\n")
            f.write("invalid_line_without_colon\n")

        result = file_filter.parse_file(config_file)

        assert result["ext"] == [".py"]
        assert result["file"] == ["README.md"]
        assert result["dir"] == ["src"]

    def test_is_likely_compressed_file_minified(self, file_filter, temp_dir):
        """Test detection of minified files."""
        test_file = os.path.join(temp_dir, "bundle.min.js")
        with open(test_file, "w") as f:
            f.write("a" * 1000)  # Long single line

        result = file_filter._is_likely_compressed_file(test_file)

        assert result is True

    def test_is_likely_compressed_file_source_map(self, file_filter, temp_dir):
        """Test detection of source map files."""
        test_file = os.path.join(temp_dir, "bundle.js.map")
        Path(test_file).touch()

        result = file_filter._is_likely_compressed_file(test_file)

        assert result is True


class TestGitignoreMatcher:
    """Tests for GitignoreMatcher."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_init_empty(self, temp_dir):
        """Test initialization with no content."""
        matcher = GitignoreMatcher(temp_dir)

        assert matcher.root_path == temp_dir
        assert matcher.spec is None

    def test_parse_content(self, temp_dir):
        """Test parsing gitignore content."""
        content = "*.pyc\n__pycache__/\nnode_modules/\n"
        matcher = GitignoreMatcher(temp_dir, content)

        assert matcher.spec is not None

    def test_parse_empty_content(self, temp_dir):
        """Test parsing empty content."""
        matcher = GitignoreMatcher(temp_dir, "")

        assert matcher.spec is None

    def test_should_ignore_no_spec(self, temp_dir):
        """Test should_ignore with no spec."""
        matcher = GitignoreMatcher(temp_dir)

        result = matcher.should_ignore("/some/path/file.py")

        assert result is False

    def test_should_ignore_file(self, temp_dir):
        """Test ignoring a file pattern."""
        content = "*.pyc"
        matcher = GitignoreMatcher(temp_dir, content)

        test_file = os.path.join(temp_dir, "test.pyc")
        result = matcher.should_ignore(test_file)

        assert result is True

    def test_should_not_ignore_unmatched(self, temp_dir):
        """Test not ignoring unmatched files."""
        content = "*.pyc"
        matcher = GitignoreMatcher(temp_dir, content)

        test_file = os.path.join(temp_dir, "test.py")
        result = matcher.should_ignore(test_file)

        assert result is False

    def test_should_ignore_directory(self, temp_dir):
        """Test ignoring a directory."""
        content = "__pycache__/"
        matcher = GitignoreMatcher(temp_dir, content)

        test_dir = os.path.join(temp_dir, "__pycache__")
        result = matcher.should_ignore(test_dir, is_dir=True)

        assert result is True

    def test_should_ignore_nested_path(self, temp_dir):
        """Test ignoring nested paths."""
        content = "node_modules/"
        matcher = GitignoreMatcher(temp_dir, content)

        nested_path = os.path.join(temp_dir, "src", "node_modules", "package")
        result = matcher.should_ignore(nested_path, is_dir=True)

        assert result is True

    def test_should_not_ignore_root(self, temp_dir):
        """Test that root path is not ignored."""
        content = "*"
        matcher = GitignoreMatcher(temp_dir, content)

        result = matcher.should_ignore(temp_dir)

        assert result is False

    def test_from_file_existing(self, temp_dir):
        """Test creating matcher from existing .gitignore file."""
        gitignore_path = os.path.join(temp_dir, ".gitignore")
        with open(gitignore_path, "w") as f:
            f.write("*.log\n")

        matcher = GitignoreMatcher.from_file(temp_dir)

        assert matcher.spec is not None
        test_file = os.path.join(temp_dir, "debug.log")
        assert matcher.should_ignore(test_file) is True

    def test_from_file_missing(self, temp_dir):
        """Test creating matcher when .gitignore doesn't exist."""
        matcher = GitignoreMatcher.from_file(temp_dir)

        assert matcher.spec is None


class TestFileFilterEdgeCases:
    """Tests for FileFilter edge cases."""

    @pytest.fixture
    def file_filter(self):
        return FileFilter()

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_check_compressed_content_sample_empty(self, file_filter, temp_dir):
        """Test compressed content check with empty file."""
        test_file = os.path.join(temp_dir, "empty.js")
        Path(test_file).touch()

        result = file_filter._check_compressed_content_sample(test_file)

        assert result is False

    def test_check_compressed_content_sample_long_line(self, file_filter, temp_dir):
        """Test detection of long lines."""
        test_file = os.path.join(temp_dir, "long_line.js")
        with open(test_file, "w") as f:
            f.write("a" * 600)  # Line longer than 500 chars

        result = file_filter._check_compressed_content_sample(test_file)

        assert result is True

    def test_check_compressed_content_sample_few_lines(self, file_filter, temp_dir):
        """Test detection of files with few lines but large content."""
        test_file = os.path.join(temp_dir, "dense.js")
        with open(test_file, "w") as f:
            f.write("abc" * 200)  # 600 chars but only 1 line

        result = file_filter._check_compressed_content_sample(test_file)

        assert result is True

    def test_check_compressed_content_sample_low_whitespace(self, file_filter, temp_dir):
        """Test detection of low whitespace ratio."""
        test_file = os.path.join(temp_dir, "compact.js")
        with open(test_file, "w") as f:
            # Content with very little whitespace
            f.write("abcdefghij" * 50)  # 500 chars, no whitespace

        result = file_filter._check_compressed_content_sample(test_file)

        assert result is True

    def test_is_compressed_content_with_stats(self, file_filter, temp_dir):
        """Test detailed content analysis."""
        test_file = os.path.join(temp_dir, "test.js")
        with open(test_file, "w") as f:
            # Create content with specific properties
            lines = ["x" * 1000 for _ in range(10)]  # Long lines
            f.write("\n".join(lines))

        result = file_filter._is_compressed_content(test_file)

        # Should detect long lines
        assert result is True

    def test_should_include_large_file(self, file_filter, temp_dir):
        """Test exclusion of very large files when using explicit rules.

        Note: File size check is only performed when inclusions or exclusions are provided.
        Without explicit rules, the filter uses a simplified path that doesn't check size.
        """
        test_file = os.path.join(temp_dir, "large_file.txt")
        # Create a file larger than max size (1MB)
        with open(test_file, "wb") as f:
            f.write(b"x" * (2 * 1024 * 1024))  # 2MB > 1MB threshold

        # Verify the file is actually large
        file_size_mb = os.path.getsize(test_file) / (1024 * 1024)
        assert file_size_mb > 1.0, f"Test file should be > 1MB, got {file_size_mb:.2f}MB"

        # File size is only checked when explicit rules are provided
        # Test with exclusion rules - large file should be excluded
        exclusions = {"ext": [], "file": [], "dir": []}
        with patch('app.domain.codebase.filter.is_text_file', return_value=True), \
             patch('app.domain.codebase.filter.is_encrypted_path', return_value=False):
            result = file_filter.should_include(test_file, exclusions=exclusions)

            # The file size check should exclude this file when rules are provided
            assert result is False, f"Large file ({file_size_mb:.2f}MB) should be excluded when rules are provided"


class TestCodebaseIntegration:
    """Integration-style tests for codebase module."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a typical project structure
            os.makedirs(os.path.join(tmpdir, "src", "components"))
            os.makedirs(os.path.join(tmpdir, "node_modules", "package"))
            os.makedirs(os.path.join(tmpdir, ".git"))

            # Create files
            Path(os.path.join(tmpdir, "src", "app.py")).touch()
            Path(os.path.join(tmpdir, "src", "components", "widget.py")).touch()
            Path(os.path.join(tmpdir, "README.md")).touch()
            Path(os.path.join(tmpdir, ".gitignore")).write_text("__pycache__/\n*.pyc\n")

            yield tmpdir

    def test_file_filter_with_real_project(self, temp_project):
        """Test FileFilter with a real project structure."""
        file_filter = FileFilter()

        # Should include source files
        src_file = os.path.join(temp_project, "src", "app.py")
        with patch('app.domain.codebase.filter.is_text_file', return_value=True), \
             patch('app.domain.codebase.filter.is_encrypted_path', return_value=False):
            assert file_filter.should_include(src_file) is True

        # Should exclude node_modules
        nm_file = os.path.join(temp_project, "node_modules", "package", "index.js")
        assert file_filter.should_include(nm_file) is False

        # Should exclude .git
        git_file = os.path.join(temp_project, ".git", "config")
        assert file_filter.should_include(git_file) is False

    def test_gitignore_matcher_with_real_project(self, temp_project):
        """Test GitignoreMatcher with a real .gitignore file."""
        matcher = GitignoreMatcher.from_file(temp_project)

        # Should ignore __pycache__
        pycache_dir = os.path.join(temp_project, "__pycache__")
        assert matcher.should_ignore(pycache_dir, is_dir=True) is True

        # Should ignore .pyc files
        pyc_file = os.path.join(temp_project, "test.pyc")
        assert matcher.should_ignore(pyc_file) is True

        # Should not ignore .py files
        py_file = os.path.join(temp_project, "test.py")
        assert matcher.should_ignore(py_file) is False
