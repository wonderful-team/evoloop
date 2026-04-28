"""
Unit tests for edit safety mechanisms (hash verification, concurrency protection).

pytest tests/unit/domain/tools/test_edit_safety.py -v
"""

import hashlib
import os
import tempfile

import pytest

from app.domain.tools.files.edit_file import handle_edit
from app.domain.tools.schemas import EditFileRequest
from app.core.tools import get_working_directory
import uuid
from app.core.file import safe_read_with_hash


class TestEditSafety:
    """Validate that safety mechanisms still work after upgrade."""

    @pytest.fixture
    def sample_file(self):
        root = get_working_directory(None)
        path = os.path.join(root, f"safety_test_{uuid.uuid4().hex}.py")
        content = "def foo():\n    return True\n"
        with open(path, 'w') as f:
            f.write(content)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_hash_mismatch_triggers_rollback(self, sample_file):
        wrong_hash = "00000000000000000000000000000000"
        result = await handle_edit(
            EditFileRequest(
                path=sample_file,
                target="    return True",
                content="    return False",
                allow_multiple=False,
                expected_hash=wrong_hash,
                verify_types=False,
                config=None
            )
        )
        assert "hash" in result.lower() or "mismatch" in result.lower() or "concurrent" in result.lower()

        # File should be unchanged
        with open(sample_file) as f:
            assert "return True" in f.read()

    @pytest.mark.asyncio
    async def test_hash_match_allows_write(self, sample_file):
        file_content, _, stats = safe_read_with_hash(sample_file)
        correct_hash = stats.content_hash

        result = await handle_edit(
            EditFileRequest(
                path=sample_file,
                target="    return True",
                content="    return False",
                allow_multiple=False,
                expected_hash=correct_hash,
                verify_types=False,
                config=None
            )
        )
        assert "success" in result.lower() or "✅" in result

        with open(sample_file) as f:
            assert "return False" in f.read()

    @pytest.mark.asyncio
    async def test_no_hash_still_writes(self, sample_file):
        result = await handle_edit(
            EditFileRequest(
                path=sample_file,
                target="    return True",
                content="    return False",
                allow_multiple=False,
                expected_hash=None,
                verify_types=False,
                config=None
            )
        )
        assert "success" in result.lower() or "✅" in result

        with open(sample_file) as f:
            assert "return False" in f.read()

    @pytest.mark.asyncio
    async def test_concurrent_modification_detected(self, sample_file):
        file_content, _, stats = safe_read_with_hash(sample_file)
        correct_hash = stats.content_hash

        # Simulate external modification between read and write
        with open(sample_file, 'w') as f:
            f.write("# modified externally\n")

        result = await handle_edit(
            EditFileRequest(
                path=sample_file,
                target="    return True",
                content="    return False",
                allow_multiple=False,
                expected_hash=correct_hash,
                verify_types=False,
                config=None
            )
        )
        assert "hash" in result.lower() or "mismatch" in result.lower() or "concurrent" in result.lower()

        # External modification should remain (or at least not be our edit)
        with open(sample_file) as f:
            content = f.read()
        assert "modified externally" in content or "return True" not in content
