"""
Regression tests for API compatibility.

Ensure existing callers of edit_file and related utilities are not broken.
pytest tests/regression/test_edit_api_compat.py -v
"""

import inspect
import os
import tempfile

import pytest

from app.domain.tools.files.edit_file import edit_file, handle_edit

# edit_file is a StructuredTool; inspect its underlying coroutine for signature
_edit_file_func = edit_file.coroutine if hasattr(edit_file, 'coroutine') else edit_file
from app.core.file import apply_edit_with_verification


class TestEditAPICompat:
    """Validate that existing APIs remain stable."""

    def test_edit_file_signature_unchanged(self):
        """edit_file must keep the same parameter names and order."""
        sig = inspect.signature(_edit_file_func)
        params = list(sig.parameters.keys())
        expected = [
            "path",
            "target",
            "replacement",
            "edits",
            "allow_multiple",
            "expected_hash",
            "dry_run",
            "verify_types",
            "config",
        ]
        assert params == expected, f"Signature changed: {params}"

    def test_edit_file_defaults_unchanged(self):
        """Default values for existing parameters must not change."""
        sig = inspect.signature(_edit_file_func)
        defaults = {
            p.name: p.default
            for p in sig.parameters.values()
            if p.default is not inspect.Parameter.empty
        }
        assert defaults.get("allow_multiple") is False
        assert defaults.get("expected_hash") is None
        assert defaults.get("dry_run") is False
        assert defaults.get("verify_types") is True

    def test_apply_edit_with_verification_still_exists(self):
        """Other modules may call this directly; it must remain importable."""
        assert callable(apply_edit_with_verification)

    @pytest.mark.asyncio
    async def test_dry_run_still_works(self):
        from app.core.tools import get_working_directory
        import uuid

        root = get_working_directory(None)
        path = os.path.join(root, f"compat_test_{uuid.uuid4().hex}.py")
        try:
            with open(path, 'w') as f:
                f.write("def foo():\n    pass\n")
            result = await edit_file.ainvoke({
                "path": path,
                "target": "    pass",
                "replacement": "    return",
                "dry_run": True
            })
            assert "preview" in result.lower() or "diff" in result.lower() or "Preview" in result
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @pytest.mark.asyncio
    async def test_expected_hash_still_works(self):
        from app.core.file import safe_read_with_hash
        from app.core.tools import get_working_directory
        import uuid

        root = get_working_directory(None)
        path = os.path.join(root, f"compat_test_{uuid.uuid4().hex}.py")
        try:
            with open(path, 'w') as f:
                f.write("def foo():\n    pass\n")
            _, _, stats = safe_read_with_hash(path)
            result = await edit_file.ainvoke({
                "path": path,
                "target": "    pass",
                "replacement": "    return",
                "expected_hash": stats.content_hash
            })
            assert "success" in result.lower() or "✅" in result
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_handle_edit_signature_stable(self):
        sig = inspect.signature(handle_edit)
        params = list(sig.parameters.keys())
        expected = [
            "request",
        ]
        assert params == expected, f"handle_edit signature changed: {params}"
