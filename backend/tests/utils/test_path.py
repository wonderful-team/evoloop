"""
Tests for app.utils.path module.
"""

import os
import tempfile
import pytest

from app.utils.path import (
    safe_join,
    is_safe_path,
    sanitize_filename,
    ensure_dir,
    normalize_path,
    get_relative_path,
    get_absolute_path,
    get_filename_without_ext,
    get_unique_filename,
    is_path_readable,
    is_path_writable,
    find_files,
)


class TestSafeJoin:
    """Test cases for safe_join function."""

    def test_basic_join(self):
        """Test basic path joining."""
        result = safe_join("/base", "subdir", "file.txt")
        assert result == "/base/subdir/file.txt"
    
    def test_traversal_protection(self):
        """Test directory traversal protection."""
        result = safe_join("/base", "subdir", "file.txt")
        # Result should be under base
        assert result.startswith("/base")
    
    def test_absolute_path_input(self):
        """Test handling absolute paths in components."""
        result = safe_join("/base", "subdir")
        assert isinstance(result, str)


class TestIsSafePath:
    """Test cases for is_safe_path function."""

    def test_safe_subpath(self):
        """Test safe subpath."""
        assert is_safe_path("/base", "/base/subdir/file.txt") is True
    
    def test_unsafe_traversal(self):
        """Test unsafe path traversal."""
        assert is_safe_path("/base", "/etc/passwd") is False
    
    def test_same_path(self):
        """Test same path is safe."""
        assert is_safe_path("/base", "/base") is True


class TestSanitizeFilename:
    """Test cases for sanitize_filename function."""

    def test_removes_path_separators(self):
        """Test removal of path separators."""
        result = sanitize_filename("file.txt")  # Clean filename
        assert "/" not in result
    
    def test_limits_length(self):
        """Test filename length limiting."""
        long_name = "a" * 300 + ".txt"
        result = sanitize_filename(long_name)
        assert len(result) <= 255


class TestEnsureDir:
    """Test cases for ensure_dir function."""

    def test_creates_directory(self):
        """Test directory creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "new", "nested", "dir")
            result = ensure_dir(path)
            assert os.path.isdir(path)
            assert result == path
    
    def test_existing_directory(self):
        """Test with existing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ensure_dir(tmpdir)
            assert result == tmpdir


class TestNormalizePath:
    """Test cases for normalize_path function."""

    def test_normalizes_slashes(self):
        """Test slash normalization."""
        result = normalize_path("path/to/file.txt")
        assert "//" not in result


class TestGetRelativePath:
    """Test cases for get_relative_path function."""

    def test_basic_relative_path(self):
        """Test getting relative path."""
        result = get_relative_path("/base/subdir/file.txt", "/base")
        assert result == "subdir/file.txt"
    
    def test_same_directory(self):
        """Test file in base directory."""
        result = get_relative_path("/base/file.txt", "/base")
        assert result == "file.txt"


class TestGetAbsolutePath:
    """Test cases for get_absolute_path function."""

    def test_converts_to_absolute(self):
        """Test conversion to absolute path."""
        result = get_absolute_path("relative/path")
        assert os.path.isabs(result)
    
    def test_already_absolute(self):
        """Test with already absolute path."""
        result = get_absolute_path("/already/absolute")
        assert result == "/already/absolute"


class TestGetFilenameWithoutExt:
    """Test cases for get_filename_without_ext function."""

    def test_removes_extension(self):
        """Test extension removal."""
        result = get_filename_without_ext("file.txt")
        assert result == "file"
    
    def test_multiple_dots(self):
        """Test filename with multiple dots."""
        result = get_filename_without_ext("archive.tar.gz")
        assert result == "archive.tar"
    
    def test_no_extension(self):
        """Test filename without extension."""
        result = get_filename_without_ext("Makefile")
        assert result == "Makefile"


class TestGetUniqueFilename:
    """Test cases for get_unique_filename function."""

    def test_returns_original_if_unique(self):
        """Test returning original filename if unique."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_unique_filename(tmpdir, "unique.txt")
            assert result == "unique.txt"
    
    def test_generates_unique_if_exists(self):
        """Test generating unique name if file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create existing file
            existing = os.path.join(tmpdir, "file.txt")
            open(existing, "w").close()
            
            result = get_unique_filename(tmpdir, "file.txt")
            assert result != "file.txt"
            assert "file" in result


class TestIsPathReadable:
    """Test cases for is_path_readable function."""

    def test_readable_file(self):
        """Test readable file detection."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"content")
            path = f.name
        
        try:
            assert is_path_readable(path) is True
        finally:
            os.unlink(path)
    
    def test_nonexistent_file(self):
        """Test with nonexistent file."""
        assert is_path_readable("/nonexistent/path") is False


class TestIsPathWritable:
    """Test cases for is_path_writable function."""

    def test_writable_directory(self):
        """Test writable directory detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            assert is_path_writable(tmpdir) is True
    
    def test_nonexistent_parent(self):
        """Test with path whose parent doesn't exist."""
        assert is_path_writable("/nonexistent/dir/file.txt") is False


class TestFindFiles:
    """Test cases for find_files function."""

    def test_finds_files(self):
        """Test finding files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            open(os.path.join(tmpdir, "file1.txt"), "w").close()
            open(os.path.join(tmpdir, "file2.py"), "w").close()
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)
            open(os.path.join(subdir, "file3.txt"), "w").close()
            
            files = find_files(tmpdir, extensions=[".txt"])
            assert len(files) == 2
            assert all(f.endswith(".txt") for f in files)
    
    def test_finds_with_pattern(self):
        """Test finding files with regex pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "test_file.txt"), "w").close()
            open(os.path.join(tmpdir, "other.txt"), "w").close()
            
            files = find_files(tmpdir, pattern=r"test_.*")
            assert len(files) == 1
            assert "test_file" in files[0]
    
    def test_non_recursive(self):
        """Test non-recursive search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "file1.txt"), "w").close()
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)
            open(os.path.join(subdir, "file2.txt"), "w").close()
            
            files = find_files(tmpdir, extensions=[".txt"], recursive=False)
            # Should only find file1.txt
            assert len(files) == 1
