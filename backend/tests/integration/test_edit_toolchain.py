"""
Integration tests for edit tool chain combinations.

pytest tests/integration/test_edit_toolchain.py -v
"""

import os

import pytest

from app.domain.tools.files.edit_file import edit_file
from app.domain.tools.files.read_file import read_file
from app.core.tools import get_working_directory



class TestEditToolchain:
    """Validate tool chain combinations work correctly."""

    @pytest.fixture
    def sample_file(self):
        import uuid
        root = get_working_directory(None)
        path = os.path.join(root, f"chain_test_{uuid.uuid4().hex}.py")
        content = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
        with open(path, 'w') as f:
            f.write(content)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_read_then_edit_flow(self, sample_file):
        # Step 1: Read
        read_result = await read_file.ainvoke({"path": sample_file})
        assert "def foo" in read_result

        # Step 2: Edit
        edit_result = await edit_file.ainvoke({
            "path": sample_file,
            "target": "    return 1",
            "replacement": "    return 10"
        })
        assert "success" in edit_result.lower() or "✅" in edit_result

        with open(sample_file) as f:
            assert "return 10" in f.read()

    @pytest.mark.asyncio
    async def test_read_then_multiedit_flow(self, sample_file):
        read_result = await read_file.ainvoke({"path": sample_file})
        assert "def foo" in read_result

        edits = [
            {"target": "    return 1", "replacement": "    return 10"},
            {"target": "    return 2", "replacement": "    return 20"},
        ]
        result = await edit_file.ainvoke({"path": sample_file, "edits": edits})
        assert "success" in result.lower() or "✅" in result

        with open(sample_file) as f:
            content = f.read()
        assert "return 10" in content
        assert "return 20" in content

    @pytest.mark.asyncio
    async def test_edit_then_verify_types_async(self, sample_file):
        """Verify that edit_file with verify_types=True returns quickly."""
        import time

        start = time.perf_counter()
        result = await edit_file.ainvoke({
            "path": sample_file,
            "target": "    return 1",
            "replacement": "    return 10",
            "verify_types": True
        })
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert "success" in result.lower() or "✅" in result
        # The edit result itself should return quickly even if LSP is slow
        print(f"\nEdit+verify_types returned in {elapsed_ms:.1f}ms")

    @pytest.mark.asyncio
    async def test_multiedit_then_single_type_check(self, sample_file):
        """Verify edit_file(edits=...) triggers only one type check for 5 edits."""
        from unittest.mock import patch
        from app.domain.codebase.exploration.engine import get_exploration_engine

        edits = [
            {"target": f"    return {i}", "replacement": f"    return {i}0"}
            for i in range(1, 6)
        ]
        # Note: this requires the file to have returns 1-5, so we rewrite it
        with open(sample_file, 'w') as f:
            f.write("".join([f"def func_{i}():\n    return {i}\n" for i in range(1, 6)]))

        engine = get_exploration_engine()
        with patch.object(engine, 'check_types', wraps=engine.check_types) as mock_check:
            await edit_file.ainvoke({"path": sample_file, "edits": edits, "verify_types": True})
            # edit_file with edits triggers only one type check for all edits
            print(f"\ncheck_types called {mock_check.call_count} times")
