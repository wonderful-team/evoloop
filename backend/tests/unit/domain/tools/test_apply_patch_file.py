"""
Unit tests for apply_patch_file tool.

pytest tests/unit/domain/tools/test_apply_patch_file.py -v
"""

import os

import pytest

from app.core.tools import get_working_directory
from app.domain.tools.files.apply_patch_file import apply_patch_file, parse_patch


class TestApplyPatchFile:
    """Validate apply_patch_file behavior."""

    @pytest.fixture
    def sample_file(self):
        import uuid
        
        root = get_working_directory(None)
        path = os.path.join(root, f"patch_test_{uuid.uuid4().hex}.py")
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
    async def test_patch_single_hunk(self, sample_file):
        patch_text = f"""*** Begin Patch
*** Update File: {sample_file}
@@
-def foo():
-    return 1
+def foo():
+    return 999
*** End Patch"""

        result = await apply_patch_file.ainvoke({"patch_text": patch_text})
        assert "success" in result.lower() or "applied" in result.lower()

        with open(sample_file) as f:
            content = f.read()
        assert "return 999" in content
        # Check the exact old value is gone (using line context to avoid substring match)
        assert "def foo():\n    return 1" not in content

    @pytest.mark.asyncio
    async def test_patch_multiple_hunks(self, sample_file):
        patch_text = f"""*** Begin Patch
*** Update File: {sample_file}
@@
-def foo():
-    return 1
+def foo():
+    return 10
@@
-def bar():
-    return 2
+def bar():
+    return 20
*** End Patch"""

        result = await apply_patch_file.ainvoke({"patch_text": patch_text})
        assert "success" in result.lower()

        with open(sample_file) as f:
            content = f.read()
        assert "return 10" in content
        assert "return 20" in content
        assert "return 3" in content  # unchanged

    @pytest.mark.asyncio
    async def test_patch_atomic_rollback(self, sample_file):
        import hashlib
        with open(sample_file, 'rb') as f:
            original_hash = hashlib.md5(f.read()).hexdigest()

        patch_text = f"""*** Begin Patch
*** Update File: {sample_file}
@@
-def foo():
-    return 1
+def foo():
+    return 10
@@
-this does not exist
-should fail
+replacement
*** End Patch"""

        result = await apply_patch_file.ainvoke({"patch_text": patch_text})
        assert "fail" in result.lower() or "error" in result.lower()

        with open(sample_file, 'rb') as f:
            after_hash = hashlib.md5(f.read()).hexdigest()
        assert after_hash == original_hash

    @pytest.mark.asyncio
    async def test_patch_add_file(self):
        import uuid
        root = get_working_directory(None)
        new_file = os.path.join(root, f"patch_add_test_{uuid.uuid4().hex}.py")
        patch_text = f"""*** Begin Patch
*** Add File: {new_file}
+def hello():
+    return "world"
*** End Patch"""

        result = await apply_patch_file.ainvoke({"patch_text": patch_text})
        assert "success" in result.lower()
        assert os.path.exists(new_file)
        with open(new_file) as f:
            assert "def hello()" in f.read()
        # Cleanup
        if os.path.exists(new_file):
            os.unlink(new_file)

    @pytest.mark.asyncio
    async def test_patch_delete_file(self, sample_file):
        patch_text = f"""*** Begin Patch
*** Delete File: {sample_file}
*** End Patch"""

        result = await apply_patch_file.ainvoke({"patch_text": patch_text})
        assert "success" in result.lower()
        assert not os.path.exists(sample_file)

    def test_parse_patch_invalid_syntax(self):
        patch_text = "*** Begin Patch\n*** Update File: foo.py\n+missing end"
        with pytest.raises(Exception):
            parse_patch(patch_text)
