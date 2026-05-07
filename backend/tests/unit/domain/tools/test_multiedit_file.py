"""
Unit tests for multiedit_file tool.

pytest tests/unit/domain/tools/test_multiedit_file.py -v
"""

import os

import pytest

from app.core.tools import get_working_directory
from app.domain.tools.files.multiedit_file import multiedit_file


def _extract_text(result):
    """multiedit_file returns nested tuple ((text, meta), meta). Extract the text."""
    if isinstance(result, tuple) and len(result) == 2:
        inner, _ = result
        if isinstance(inner, tuple) and len(inner) == 2:
            text, _ = inner
            return text
        return inner
    return result


class TestMultiEditFile:
    """Validate multiedit_file behavior."""

    @pytest.fixture
    def sample_file(self):
        import uuid
        
        root = get_working_directory(None)
        path = os.path.join(root, f"multiedit_test_{uuid.uuid4().hex}.py")
        content = '''def foo():
    return 1

def bar():
    return 2

def baz():
    return 3
'''
        with open(path, 'w') as f:
            f.write(content)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_multiedit_all_success(self, sample_file):
        edits = [
            {"target": "def foo():\n    return 1", "replacement": "def foo():\n    return 10"},
            {"target": "def bar():\n    return 2", "replacement": "def bar():\n    return 20"},
        ]
        result = await multiedit_file.ainvoke({"path": sample_file, "edits": edits})
        text = _extract_text(result)
        assert "success" in text.lower() or "✅" in text

        with open(sample_file) as f:
            content = f.read()
        assert "return 10" in content
        assert "return 20" in content
        assert "return 3" in content  # unchanged

    @pytest.mark.asyncio
    async def test_multiedit_atomic_rollback(self, sample_file):
        # Capture original hash
        import hashlib
        with open(sample_file, 'rb') as f:
            original_hash = hashlib.md5(f.read()).hexdigest()

        edits = [
            {"target": "def foo():\n    return 1", "replacement": "def foo():\n    return 10"},
            {"target": "this does not exist", "replacement": "should fail"},
        ]
        result = await multiedit_file.ainvoke({"path": sample_file, "edits": edits})
        text = _extract_text(result)
        assert "fail" in text.lower() or "error" in text.lower()

        # File must be unchanged
        with open(sample_file, 'rb') as f:
            after_hash = hashlib.md5(f.read()).hexdigest()
        assert after_hash == original_hash

    @pytest.mark.asyncio
    async def test_multiedit_sequential_dependency(self, sample_file):
        # Test sequential dependency: second edit targets the result of first edit
        edits = [
            {"target": "def foo():\n    return 1", "replacement": "def foo():\n    return 99"},
            {"target": "def foo():\n    return 99", "replacement": "def foo():\n    return 42"},
        ]
        result = await multiedit_file.ainvoke({"path": sample_file, "edits": edits})
        text = _extract_text(result)
        assert "success" in text.lower() or "✅" in text

        with open(sample_file) as f:
            content = f.read()
        # Final result should be 42
        assert "return 42" in content
        # Intermediate result should not exist (it's replaced)
        assert "return 99" not in content
        # Original should not exist
        assert "return 1" not in content

    @pytest.mark.asyncio
    async def test_multiedit_empty_edits(self, sample_file):
        result = await multiedit_file.ainvoke({"path": sample_file, "edits": []})
        # Empty edits list is valid and results in 0 changes
        text = _extract_text(result)
        assert "success" in text.lower() or "applied 0" in text.lower()

    @pytest.mark.asyncio
    async def test_multiedit_single_edit_equivalent(self, sample_file):
        edits = [
            {"target": "def foo():\n    return 1", "replacement": "def foo():\n    return 99"},
        ]
        result = await multiedit_file.ainvoke({"path": sample_file, "edits": edits})
        text = _extract_text(result)
        assert "success" in text.lower() or "✅" in text

        with open(sample_file) as f:
            content = f.read()
        assert "return 99" in content
