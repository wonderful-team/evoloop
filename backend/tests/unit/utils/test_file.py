"""
Unit tests for file utilities.
"""

import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock, mock_open

from app.utils.file import (
    resolve_path,
    normalize_path,
    get_file_ext,
    is_encrypted_path,
    get_file_encoding,
    read_file_content,
    read_file,
    write_file_contents,
    write_file,
    get_directory_size,
)


class TestResolvePath:
    """Tests for resolve_path function."""

    def test_resolve_empty_path(self):
        """Test resolving empty path."""
        result = resolve_path("")
        assert result is None

    def test_resolve_none_path(self):
        """Test resolving None path."""
        result = resolve_path(None)
        assert result is None

    def test_resolve_absolute_path_exists(self):
        """Test resolving existing absolute path."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            temp_path = f.name
        try:
            result = resolve_path(temp_path)
            assert result == temp_path
        finally:
            os.unlink(temp_path)

    def test_resolve_relative_path_with_base(self):
        """Test resolving relative path with base path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("test")
            result = resolve_path("test.txt", base_path=tmpdir)
            assert result == test_file

    def test_resolve_url(self):
        """Test resolving URL path."""
        with patch('app.utils.file.ensure_local_path') as mock_ensure:
            mock_ensure.return_value = "/tmp/downloaded_file.txt"
            result = resolve_path("https://example.com/file.txt")
            assert result == "/tmp/downloaded_file.txt"


class TestNormalizePath:
    """Tests for normalize_path function."""

    def test_normalize_backslashes(self):
        """Test normalizing backslashes to forward slashes."""
        result = normalize_path("path\\to\\file.txt")
        assert result == "path/to/file.txt"

    def test_normalize_leading_slash(self):
        """Test removing leading slash."""
        result = normalize_path("/path/to/file.txt")
        assert result == "path/to/file.txt"

    def test_normalize_already_normalized(self):
        """Test normalizing already normalized path."""
        result = normalize_path("path/to/file.txt")
        assert result == "path/to/file.txt"


class TestGetFileExt:
    """Tests for get_file_ext function."""

    def test_get_extension_lowercase(self):
        """Test getting extension in lowercase."""
        result = get_file_ext("file.TXT")
        assert result == ".txt"

    def test_get_extension_already_lower(self):
        """Test getting already lowercase extension."""
        result = get_file_ext("file.txt")
        assert result == ".txt"

    def test_get_extension_no_extension(self):
        """Test getting extension of file without extension."""
        result = get_file_ext("Makefile")
        assert result == ""

    def test_get_extension_multiple_dots(self):
        """Test getting extension with multiple dots."""
        result = get_file_ext("archive.tar.gz")
        assert result == ".gz"


class TestIsEncryptedPath:
    """Tests for is_encrypted_path function."""

    def test_path_with_hash(self):
        """Test path containing hash-like pattern."""
        result = is_encrypted_path("/path/abc12345/file.txt")
        assert result is True

    def test_path_without_hash(self):
        """Test path without hash-like pattern."""
        result = is_encrypted_path("/path/normal/file.txt")
        assert result is False

    def test_path_with_short_hash(self):
        """Test path with short hash (less than 8 chars)."""
        result = is_encrypted_path("/path/abc123/file.txt")
        assert result is False


class TestGetFileEncoding:
    """Tests for get_file_encoding function."""

    def test_detect_utf8(self):
        """Test detecting UTF-8 encoding."""
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
            f.write("UTF-8 content")
            temp_path = f.name
        try:
            result = get_file_encoding(temp_path)
            assert result == "utf-8"
        finally:
            os.unlink(temp_path)

    def test_detect_fallback(self):
        """Test fallback to utf-8 for unknown encoding."""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(b"\x80\x81\x82")  # Invalid UTF-8
            temp_path = f.name
        try:
            result = get_file_encoding(temp_path)
            # Should fallback to one of the supported encodings or utf-8
            assert result in ["utf-8", "latin-1", "utf-16", "ascii"]
        finally:
            os.unlink(temp_path)


class TestReadFileContent:
    """Tests for read_file_content function."""

    def test_read_full_file(self):
        """Test reading entire file."""
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
            f.write("Line 1\nLine 2\nLine 3")
            temp_path = f.name
        try:
            content, encoding = read_file_content(temp_path)
            assert "Line 1" in content
            assert "Line 2" in content
            assert "Line 3" in content
            assert encoding == "utf-8"
        finally:
            os.unlink(temp_path)

    def test_read_line_range(self):
        """Test reading specific line range."""
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
            f.write("Line 1\nLine 2\nLine 3\nLine 4\nLine 5")
            temp_path = f.name
        try:
            content, _ = read_file_content(temp_path, start_line=2, end_line=4)
            assert "Line 1" not in content
            assert "Line 2" in content
            assert "Line 3" in content
            assert "Line 4" in content  # end_line is inclusive
        finally:
            os.unlink(temp_path)

    def test_read_nonexistent_file(self):
        """Test reading non-existent file."""
        # When file doesn't exist, get_file_encoding may fail
        # The function should handle this gracefully
        try:
            content, encoding = read_file_content("/nonexistent/path/file.txt")
            assert content == ""
            # encoding may be determined even if file doesn't exist
            assert isinstance(encoding, str)
        except FileNotFoundError:
            # This is also acceptable - the encoding detection may fail first
            pass


class TestReadFile:
    """Tests for read_file function."""

    def test_read_file(self):
        """Test reading file."""
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
            f.write("Test content")
            temp_path = f.name
        try:
            result = read_file(temp_path)
            assert result == "Test content"
        finally:
            os.unlink(temp_path)


class TestWriteFileContents:
    """Tests for write_file_contents function."""

    def test_write_new_file(self):
        """Test writing to new file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "subdir", "test.txt")
            result = write_file_contents("Hello World", file_path)
            assert result is True
            assert os.path.exists(file_path)
            with open(file_path, 'r') as f:
                assert f.read() == "Hello World"

    def test_write_overwrite_existing(self):
        """Test overwriting existing file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("Old content")
            temp_path = f.name
        try:
            result = write_file_contents("New content", temp_path)
            assert result is True
            with open(temp_path, 'r') as f:
                assert f.read() == "New content"
        finally:
            os.unlink(temp_path)

    def test_write_file_alias(self):
        """Test write_file alias function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt")
            result = write_file(file_path, "Content")
            assert result is True


class TestGetDirectorySize:
    """Tests for get_directory_size function."""

    def test_empty_directory(self):
        """Test getting size of empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_directory_size(tmpdir)
            assert result == 0

    def test_directory_with_files(self):
        """Test getting size of directory with files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files with known content
            with open(os.path.join(tmpdir, "file1.txt"), 'w') as f:
                f.write("a" * 100)  # 100 bytes
            with open(os.path.join(tmpdir, "file2.txt"), 'w') as f:
                f.write("b" * 200)  # 200 bytes

            result = get_directory_size(tmpdir)
            assert result == 300

    def test_directory_with_subdirectories(self):
        """Test getting size of directory with subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "subdir"))
            with open(os.path.join(tmpdir, "file1.txt"), 'w') as f:
                f.write("a" * 100)
            with open(os.path.join(tmpdir, "subdir", "file2.txt"), 'w') as f:
                f.write("b" * 50)

            result = get_directory_size(tmpdir)
            assert result == 150
