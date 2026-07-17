"""Unit tests for app.core.file.hash."""

import tempfile
from pathlib import Path

from app.core.file.hash import (
    compute_content_hash,
    compute_file_hash,
    compute_hash,
    compute_md5,
    compute_sha256,
    compute_state_id,
    compute_version_hash,
)


class TestHash:
    def test_compute_md5_string(self):
        assert compute_md5("hello") == "5d41402abc4b2a76b9719d911017c592"

    def test_compute_md5_bytes(self):
        assert compute_md5(b"hello") == "5d41402abc4b2a76b9719d911017c592"

    def test_compute_md5_empty(self):
        assert compute_md5("") == "d41d8cd98f00b204e9800998ecf8427e"

    def test_compute_sha256_string(self):
        h = compute_sha256("hello")
        expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        assert h == expected

    def test_compute_sha256_bytes(self):
        h = compute_sha256(b"hello")
        assert h == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

    def test_compute_hash_default_md5(self):
        assert compute_hash("data") == compute_md5("data")

    def test_compute_hash_sha256(self):
        assert compute_hash("data", algorithm="sha256") == compute_sha256("data")

    def test_compute_hash_truncated(self):
        h = compute_hash("data", length=8)
        assert len(h) == 8
        assert h == compute_md5("data")[:8]

    def test_compute_file_hash(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("file content")
            path = f.name
        try:
            h = compute_file_hash(path)
            assert isinstance(h, str)
            assert len(h) == 32
            expected = compute_md5("file content")
            assert h == expected
        finally:
            Path(path).unlink(missing_ok=True)

    def test_compute_file_hash_sha256(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("data")
            path = f.name
        try:
            h = compute_file_hash(path, algo="sha256")
            expected = compute_sha256("data")
            assert h == expected
        finally:
            Path(path).unlink(missing_ok=True)

    def test_compute_file_hash_nonexistent(self):
        h = compute_file_hash("/nonexistent/file.txt")
        assert h == ""

    def test_compute_version_hash(self):
        h = compute_version_hash("v1", "component-a")
        assert len(h) == 12
        assert isinstance(h, str)

    def test_compute_state_id(self):
        h = compute_state_id("proj-1", "task-2")
        assert len(h) == 8
        assert isinstance(h, str)

    def test_compute_content_hash(self):
        h = compute_content_hash("some content")
        assert len(h) == 32
        assert h == compute_md5("some content")

    def test_compute_content_hash_truncated(self):
        h = compute_content_hash("content", length=6)
        assert len(h) == 6
