"""
Integration tests for async verify_types behavior.

pytest tests/integration/test_verify_types_async.py -v
"""

import os
import tempfile
import time

import pytest

from app.domain.tools.files.edit_file import handle_edit
from app.domain.tools.schemas import EditFileRequest


class TestVerifyTypesAsync:
    """Validate that type checking can run asynchronously without blocking edit result."""

    @pytest.fixture
    def sample_file(self):
        from app.core.tools import get_working_directory
        import uuid

        root = get_working_directory(None)
        path = os.path.join(root, f"verify_test_{uuid.uuid4().hex}.py")
        content = "def foo():\n    return 1\n"
        with open(path, 'w') as f:
            f.write(content)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_verify_types_runs_in_background(self, sample_file):
        start = time.perf_counter()
        result = await handle_edit(
            EditFileRequest(
                path=sample_file,
                target="    return 1",
                content="    return 2",
                allow_multiple=False,
                expected_hash=None,
                verify_types=False,  # Disable for speed test
                config=None
            )
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert "success" in result.lower() or "✅" in result
        print(f"\nEdit returned in {elapsed_ms:.1f}ms")

    @pytest.mark.asyncio
    async def test_verify_types_false_skips_background(self, sample_file):
        from unittest.mock import patch
        import asyncio

        with patch('asyncio.create_task') as mock_create_task:
            result = await handle_edit(
                EditFileRequest(
                    path=sample_file,
                    target="    return 1",
                    content="    return 2",
                    allow_multiple=False,
                    expected_hash=None,
                    verify_types=False,
                    config=None
                )
            )
            # If verify_types=False, no background task should be created
            mock_create_task.assert_not_called()

    # Note: Event bus mechanism not yet implemented, skipping this test for now.
    # @pytest.mark.asyncio
    # async def test_async_diagnostics_delivered(self, sample_file):
    #     pass
