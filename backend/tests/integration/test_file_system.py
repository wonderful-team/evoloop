"""
Integration tests for file system operations.
Tests actual file operations in temp directories.
"""

import os
import pytest
import tempfile
import asyncio
from pathlib import Path


@pytest.mark.integration
class TestFileOperations:
    """Integration tests for file operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_read_write_file(self, temp_dir):
        """Test reading and writing files."""
        from app.utils.file import read_file_content, write_file_contents

        test_file = os.path.join(temp_dir, "test.txt")
        test_content = "Hello, World!\nThis is a test."

        # Write file
        result = write_file_contents(test_content, test_file)
        assert result is True
        assert os.path.exists(test_file)

        # Read file
        content, encoding = read_file_content(test_file)
        assert content == test_content
        assert encoding == "utf-8"

    def test_read_file_line_range(self, temp_dir):
        """Test reading specific line ranges."""
        from app.utils.file import read_file_content

        test_file = os.path.join(temp_dir, "lines.txt")
        lines = [f"Line {i}" for i in range(1, 11)]

        with open(test_file, "w") as f:
            f.write("\n".join(lines))

        # Read lines 3-5
        content, _ = read_file_content(test_file, start_line=3, end_line=5)
        assert "Line 3" in content
        assert "Line 5" in content
        assert "Line 1" not in content
        assert "Line 10" not in content

    def test_write_file_creates_directories(self, temp_dir):
        """Test that write creates parent directories."""
        from app.utils.file import write_file_contents

        nested_file = os.path.join(temp_dir, "a", "b", "c", "file.txt")
        result = write_file_contents("content", nested_file)

        assert result is True
        assert os.path.exists(nested_file)

    def test_binary_file_detection(self, temp_dir):
        """Test binary file detection."""
        from app.core.file.service import is_binary_file

        # Text file
        text_file = os.path.join(temp_dir, "text.txt")
        with open(text_file, "w") as f:
            f.write("Hello, World!")
        assert is_binary_file(text_file) is False

        # Binary file
        binary_file = os.path.join(temp_dir, "binary.bin")
        with open(binary_file, "wb") as f:
            f.write(b"\x00\x01\x02\x03")
        assert is_binary_file(binary_file) is True

    def test_file_encoding_detection(self, temp_dir):
        """Test file encoding detection."""
        from app.utils.file import get_file_encoding

        # UTF-8 file
        utf8_file = os.path.join(temp_dir, "utf8.txt")
        with open(utf8_file, "w", encoding="utf-8") as f:
            f.write("Hello 世界")
        assert get_file_encoding(utf8_file) == "utf-8"


@pytest.mark.integration
class TestDirectoryOperations:
    """Integration tests for directory operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory with some files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some files
            Path(tmpdir, "file1.py").write_text("print('hello')")
            Path(tmpdir, "file2.txt").write_text("hello")
            Path(tmpdir, "subdir").mkdir()
            Path(tmpdir, "subdir", "file3.py").write_text("x = 1")
            yield tmpdir

    def test_walk_tree(self, temp_dir):
        """Test directory tree walking."""
        from app.core.file.service import walk_tree

        files = list(walk_tree(temp_dir))
        assert len(files) >= 3

        # Check that we found Python files
        py_files = [f for f in files if f.endswith(".py")]
        assert len(py_files) == 2

    def test_walk_tree_with_filter(self, temp_dir):
        """Test walking with filter."""
        from app.core.file.service import walk_tree

        # Only .py files
        files = list(walk_tree(temp_dir, filter_func=lambda p: p.endswith(".py")))
        assert len(files) == 2
        assert all(f.endswith(".py") for f in files)

    def test_walk_tree_excludes_hidden(self, temp_dir):
        """Test that hidden files are excluded."""
        from app.core.file.service import walk_tree

        # Create hidden file
        Path(temp_dir, ".hidden").write_text("secret")

        files = list(walk_tree(temp_dir))
        hidden_files = [f for f in files if ".hidden" in f]
        assert len(hidden_files) == 0

    def test_get_directory_size(self, temp_dir):
        """Test getting directory size."""
        from app.utils.file import get_directory_size

        size = get_directory_size(temp_dir)
        assert size > 0


@pytest.mark.integration
class TestGitOperations:
    """Integration tests for Git operations."""

    @pytest.fixture
    def git_repo(self):
        """Create a temporary git repository."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize git repo
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)

            # Create a file and commit
            Path(tmpdir, "file.txt").write_text("hello")
            subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True)

            yield tmpdir

    def test_get_current_branch(self, git_repo):
        """Test getting current branch."""
        from app.utils.git import get_current_branch

        branch = get_current_branch(git_repo)
        assert branch is not None
        assert isinstance(branch, str)

    def test_is_git_repo(self, git_repo):
        """Test git repo detection."""
        from app.utils.git import is_git_repo

        assert is_git_repo(git_repo) is True

        # Non-git directory
        with tempfile.TemporaryDirectory() as tmpdir:
            assert is_git_repo(tmpdir) is False

    def test_get_git_root(self, git_repo):
        """Test getting git root."""
        from app.utils.git import get_git_root

        root = get_git_root(git_repo)
        assert root is not None
        assert os.path.samefile(root, git_repo)


@pytest.mark.integration
class TestCodebaseOperations:
    """Integration tests for codebase operations."""

    @pytest.fixture
    def codebase_dir(self):
        """Create a mock codebase directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a Python project structure
            Path(tmpdir, "src").mkdir()
            Path(tmpdir, "src", "main.py").write_text("def main():\n    pass\n")
            Path(tmpdir, "src", "utils.py").write_text("def helper():\n    pass\n")
            Path(tmpdir, "tests").mkdir()
            Path(tmpdir, "tests", "test_main.py").write_text("def test_main():\n    pass\n")
            Path(tmpdir, "README.md").write_text("# Project\n")
            yield tmpdir

    def test_filter_code_files(self, codebase_dir):
        """Test filtering code files."""
        from app.core.file.service import filter_code_files

        all_files = []
        for root, _, files in os.walk(codebase_dir):
            for f in files:
                all_files.append(os.path.join(root, f))

        code_files = filter_code_files(all_files)

        # Should include Python and markdown files
        assert any(f.endswith(".py") for f in code_files)
        assert any(f.endswith(".md") for f in code_files)

    def test_is_test_file_detection(self, codebase_dir):
        """Test test file detection."""
        from app.core.file.service import is_test_file

        assert is_test_file("test_main.py") is True
        assert is_test_file("/path/tests/test_something.py") is True
        assert is_test_file("main.py") is False
        assert is_test_file("/src/utils.py") is False
