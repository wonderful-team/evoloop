"""
Complex tests for apply_patch_file - Multi-file operations, rename, and rollback scenarios.

These tests simulate real-world Agent workflows:
  1. Multi-file refactoring (3+ files in one patch)
  2. File move/rename operations
  3. Complex rollback (partial success -> full rollback)
  4. Large scale changes (100+ hunks)
  5. Edge cases (empty files, special characters)

pytest tests/unit/domain/tools/test_apply_patch_file_complex.py -v
"""

import os
import tempfile
import pytest
import asyncio
import hashlib

from app.core.tools import get_working_directory
from app.domain.tools.files.apply_patch_file import apply_patch_file, parse_patch
from app.domain.tools.files.read_file import read_file


class TestApplyPatchFileComplex:
    """Complex scenarios for apply_patch_file."""

    @pytest.fixture
    def project_dir(self):
        """Create a mock project directory with multiple files."""
        tmpdir = tempfile.mkdtemp()
        
        # Create main.py
        with open(os.path.join(tmpdir, "main.py"), 'w') as f:
            f.write('''"""Main module."""
from utils import helper

def main():
    result = helper()
    print(result)
    return result

if __name__ == "__main__":
    main()
''')
        
        # Create utils.py
        with open(os.path.join(tmpdir, "utils.py"), 'w') as f:
            f.write('''"""Utility module."""

def helper():
    return "old_value"

def unused_func():
    pass
''')
        
        # Create config.py
        with open(os.path.join(tmpdir, "config.py"), 'w') as f:
            f.write('''"""Config module."""
DEBUG = True
TIMEOUT = 30
''')
        
        yield tmpdir
        
        # Cleanup
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_multi_file_patch_update_three_files(self, project_dir):
        """
        Agent workflow: Refactor across 3 files in one atomic patch.
        
        Scenario:
        1. Update main.py to use new function name
        2. Update utils.py to rename function
        3. Update config.py to change timeout
        """
        main_py = os.path.join(project_dir, "main.py")
        utils_py = os.path.join(project_dir, "utils.py")
        config_py = os.path.join(project_dir, "config.py")
        
        patch_text = f"""*** Begin Patch
*** Update File: {main_py}
@@
-from utils import helper
+from utils import new_helper
@@
-    result = helper()
+    result = new_helper()
@@
*** Update File: {utils_py}
@@
-def helper():
-    return "old_value"
+def new_helper():
+    return "new_value"
@@
*** Update File: {config_py}
@@
-TIMEOUT = 30
+TIMEOUT = 60
@@
*** End Patch"""

        result = await apply_patch_file.ainvoke({"patch_text": patch_text})
        assert "success" in result.lower() or "applied" in result.lower(), f"Failed: {result}"
        
        # Verify all files were updated
        with open(main_py) as f:
            main_content = f.read()
        assert "from utils import new_helper" in main_content
        assert "new_helper()" in main_content
        assert "helper()" not in main_content  # Old usage gone
        
        with open(utils_py) as f:
            utils_content = f.read()
        assert "def new_helper():" in utils_content
        assert "return \"new_value\"" in utils_content
        
        with open(config_py) as f:
            config_content = f.read()
        assert "TIMEOUT = 60" in config_content

    @pytest.mark.asyncio
    async def test_patch_with_file_rename(self, project_dir):
        """
        Agent workflow: Rename file and update imports.
        
        Scenario:
        1. Rename utils.py to helpers.py
        2. Update main.py import
        """
        main_py = os.path.join(project_dir, "main.py")
        utils_py = os.path.join(project_dir, "utils.py")
        helpers_py = os.path.join(project_dir, "helpers.py")
        
        patch_text = f"""*** Begin Patch
*** Update File: {utils_py}
*** Move to: {helpers_py}
*** Update File: {main_py}
@@
-from utils import helper
+from helpers import helper
@@
*** End Patch"""

        result = await apply_patch_file.ainvoke({"patch_text": patch_text})
        assert "success" in result.lower() or "applied" in result.lower(), f"Failed: {result}"
        
        # Verify rename
        assert not os.path.exists(utils_py), "Old file should not exist"
        assert os.path.exists(helpers_py), "New file should exist"
        
        # Verify import updated
        with open(main_py) as f:
            content = f.read()
        assert "from helpers import helper" in content

    @pytest.mark.asyncio
    async def test_complex_rollback_partial_success(self, project_dir):
        """
        Agent workflow: Complex rollback when operation fails mid-way.
        
        Scenario:
        1. Add new file (success)
        2. Update utils.py (success)
        3. Update non-existent file (FAIL)
        4. Verify rollback: new file deleted, utils.py restored
        """
        utils_py = os.path.join(project_dir, "utils.py")
        new_file = os.path.join(project_dir, "new_module.py")
        non_existent = os.path.join(project_dir, "does_not_exist.py")
        
        # Capture original hash
        with open(utils_py, 'rb') as f:
            original_hash = hashlib.md5(f.read()).hexdigest()
        
        patch_text = f"""*** Begin Patch
*** Add File: {new_file}
+def new_func():
+    return 42
*** Update File: {utils_py}
@@
-def helper():
-    return "old_value"
+def helper():
+    return "modified"
@@
*** Update File: {non_existent}
@@
-this will fail
+because file doesn't exist
@@
*** End Patch"""

        result = await apply_patch_file.ainvoke({"patch_text": patch_text})
        # Should fail
        assert "fail" in result.lower() or "error" in result.lower(), f"Should have failed: {result}"
        
        # Verify rollback
        # 1. New file should be deleted (rolled back)
        assert not os.path.exists(new_file), "New file should be rolled back (deleted)"
        
        # 2. utils.py should be restored to original
        with open(utils_py, 'rb') as f:
            current_hash = hashlib.md5(f.read()).hexdigest()
        assert current_hash == original_hash, "utils.py should be restored to original"

    @pytest.mark.asyncio
    async def test_add_delete_rename_combo(self, project_dir):
        """
        Agent workflow: Add file, delete another, rename third.
        
        All operations should succeed atomically.
        """
        utils_py = os.path.join(project_dir, "utils.py")
        config_py = os.path.join(project_dir, "config.py")
        new_config = os.path.join(project_dir, "settings.py")
        legacy_file = os.path.join(project_dir, "legacy.py")
        
        # Create legacy file to be deleted
        with open(legacy_file, 'w') as f:
            f.write("# Legacy code\n")
        
        patch_text = f"""*** Begin Patch
*** Add File: {new_config}
+\"\"\"Settings module.\"\"\"
+DEBUG = False
+TIMEOUT = 120
*** Delete File: {legacy_file}
*** Update File: {config_py}
*** Move to: {os.path.join(project_dir, "config_backup.py")}
*** End Patch"""

        result = await apply_patch_file.ainvoke({"patch_text": patch_text})
        assert "success" in result.lower(), f"Failed: {result}"
        
        # Verify
        assert os.path.exists(new_config), "New settings file should exist"
        assert not os.path.exists(legacy_file), "Legacy file should be deleted"
        assert not os.path.exists(config_py), "config.py should be renamed"
        assert os.path.exists(os.path.join(project_dir, "config_backup.py")), "config_backup.py should exist"


class TestApplyPatchFileEdgeCases:
    """Edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_file_add_content(self):
        """Agent workflow: Add content to empty file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("")  # Empty file
            empty_file = f.name
        
        try:
            patch_text = f"""*** Begin Patch
*** Update File: {empty_file}
@@
+\"\"\"New module.\"\"\"
+def main():
+    pass
@@
*** End Patch"""
            
            result = await apply_patch_file.ainvoke({"patch_text": patch_text})
            assert "success" in result.lower(), f"Failed: {result}"
            
            with open(empty_file) as f:
                content = f.read()
            assert 'def main():' in content
        finally:
            os.unlink(empty_file)

    @pytest.mark.asyncio
    async def test_unicode_and_special_chars(self):
        """Agent workflow: Handle Unicode and special characters."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write('# 中文注释\ndef hello():\n    return "世界"\n')
            unicode_file = f.name
        
        try:
            patch_text = f"""*** Begin Patch
*** Update File: {unicode_file}
@@
-# 中文注释
-# Unicode test: ñ, é, ü
@@
-    return "世界"
+    return "🌍 World"
@@
*** End Patch"""
            
            result = await apply_patch_file.ainvoke({"patch_text": patch_text})
            assert "success" in result.lower(), f"Failed: {result}"
            
            with open(unicode_file, 'r', encoding='utf-8') as f:
                content = f.read()
            assert '🌍 World' in content
        finally:
            os.unlink(unicode_file)

    @pytest.mark.asyncio
    async def test_many_hunks_single_file(self):
        """Agent workflow: 20+ hunks in single file (like bulk refactoring)."""
        lines = [f"def func_{i:03d}():\n    return {i}\n" for i in range(20)]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("\"\"\"Module.\"\"\"\n\n")
            f.write("".join(lines))
            many_hunks_file = f.name
        
        try:
            # Build patch with 10 hunks
            hunks = []
            for i in range(0, 20, 2):  # Every other function
                hunks.append(f"@@\n-def func_{i:03d}():\n-    return {i}\n+def func_{i:03d}():\n+    return {i*10}\n@@")
            
            hunks_joined = "\n".join(hunks)
            patch_text = f"""*** Begin Patch
*** Update File: {many_hunks_file}
{hunks_joined}
*** End Patch"""
            
            result = await apply_patch_file.ainvoke({"patch_text": patch_text})
            assert "success" in result.lower(), f"Failed: {result}"
            
            # Verify some changes
            with open(many_hunks_file) as f:
                content = f.read()
            assert "return 0" not in content  # func_000 was changed to return 0
            assert "return 20" in content     # func_002 was changed to return 20
        finally:
            os.unlink(many_hunks_file)


class TestAgentWorkflowSimulation:
    """Simulate complete Agent workflows using multiple tools."""

    @pytest.mark.asyncio
    async def test_agent_read_analyze_multiedit_workflow(self):
        """
        Simulate Agent: Read file -> Analyze -> Use edit_file(edits=...).
        
        This is the recommended workflow for multiple edits.
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('''class UserService:
    def create_user(self, name):
        # TODO: validate
        return {"name": name}
    
    def delete_user(self, id):
        # TODO: check permissions
        return True
''')
            service_file = f.name
        
        try:
            # Step 1: Agent reads file
            read_result = await read_file.ainvoke({"path": service_file})
            assert "class UserService" in read_result
            
            # Step 2: Agent analyzes and decides to use edit_file(edits=...)
            # for multiple TODO completions
                        
            edits = [
                {
                    "target": "    def create_user(self, name):\n        # TODO: validate",
                    "replacement": "    def create_user(self, name):\n        if not name or len(name) < 3:\n            raise ValueError(\"Invalid name\")"
                },
                {
                    "target": "    def delete_user(self, id):\n        # TODO: check permissions",
                    "replacement": "    def delete_user(self, id):\n        if not self.check_permission(\"delete\"):\n            raise PermissionError(\"No permission\")"
                }
            ]
            
            result = await edit_file.ainvoke({
                "path": service_file,
                "edits": edits
            })
            assert "success" in result.lower(), f"Failed: {result}"
            
            # Verify both changes applied
            with open(service_file) as f:
                content = f.read()
            assert "ValueError" in content
            assert "PermissionError" in content
            assert "# TODO" not in content
        finally:
            os.unlink(service_file)

    @pytest.mark.asyncio
    async def test_agent_large_refactor_with_patch(self):
        """
        Simulate Agent: Large refactoring requiring apply_patch_file.
        
        Scenario: Extract common functionality into new module.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create original files
            api_file = os.path.join(tmpdir, "api.py")
            models_file = os.path.join(tmpdir, "models.py")
            utils_file = os.path.join(tmpdir, "utils.py")
            
            with open(api_file, 'w') as f:
                f.write('''"""API module."""
def get_user(id):
    # Validate ID
    if not id or id <= 0:
        raise ValueError("Invalid ID")
    return {"id": id}

def create_order(user_id, items):
    # Validate ID
    if not user_id or user_id <= 0:
        raise ValueError("Invalid ID")
    return {"order_id": 1, "items": items}
''')
            
            with open(models_file, 'w') as f:
                f.write('''"""Models module."""
def save_model(data):
    # Validate ID
    if "id" not in data:
        raise ValueError("Missing ID")
    return True
''')
            
            # Agent uses apply_patch_file to:
            # 1. Create utils.py with validation function
            # 2. Update api.py to use utils.validate_id
            # 3. Update models.py to use utils.validate_id
            
            patch_text = f"""*** Begin Patch
*** Add File: {utils_file}
+\"\"\"Utility functions.\"\"\"
+
+def validate_id(id_value):
+    \"\"\"Validate that ID is positive integer.\"\"\"\n+    if not id_value or id_value <= 0:
+        raise ValueError(f"Invalid ID: {{id_value}}")
+    return True
*** Update File: {api_file}
@@
+from utils import validate_id
+
@@
-    # Validate ID
-    if not id or id <= 0:
-        raise ValueError("Invalid ID")
+    validate_id(id)
@@
-    # Validate ID
-    if not user_id or user_id <= 0:
-        raise ValueError("Invalid ID")
+    validate_id(user_id)
@@
*** Update File: {models_file}
@@
+from utils import validate_id
+
@@
-    # Validate ID
-    if "id" not in data:
-        raise ValueError("Missing ID")
+    validate_id(data.get("id"))
@@
*** End Patch"""
            
            result = await apply_patch_file.ainvoke({"patch_text": patch_text})
            assert "success" in result.lower(), f"Failed: {result}"
            
            # Verify
            with open(utils_file) as f:
                assert "def validate_id" in f.read()
            
            with open(api_file) as f:
                api_content = f.read()
                assert "from utils import validate_id" in api_content
                assert "validate_id(id)" in api_content
                assert "# Validate ID" not in api_content  # Old code gone
            
            with open(models_file) as f:
                models_content = f.read()
                assert "from utils import validate_id" in models_content


class TestStressAndConcurrency:
    """Stress tests and concurrent operation handling."""

    @pytest.mark.asyncio
    async def test_rapid_consecutive_patches(self):
        """Apply 10 patches rapidly to the same file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def counter():\n    return 0\n')
            rapid_file = f.name
        
        try:
            for i in range(10):
                patch_text = f"""*** Begin Patch
*** Update File: {rapid_file}
@@
-    return {i}
+    return {i+1}
@@
*** End Patch"""
                
                result = await apply_patch_file.ainvoke({"patch_text": patch_text})
                assert "success" in result.lower(), f"Failed at iteration {i}: {result}"
            
            # Verify final state
            with open(rapid_file) as f:
                content = f.read()
            assert "return 10" in content
        finally:
            os.unlink(rapid_file)

    @pytest.mark.asyncio
    async def test_large_file_2000_lines(self):
        """Test patch application on 2000 line file."""
        lines = [f"line_{i:04d} = {i}\n" for i in range(2000)]
        lines[500] = "TARGET_LINE = 500\n"
        lines[1500] = "ANOTHER_TARGET = 1500\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("\"\"\"Large file.\"\"\"\n")
            f.write("".join(lines))
            large_file = f.name
        
        try:
            patch_text = f"""*** Begin Patch
*** Update File: {large_file}
@@
-TARGET_LINE = 500
+TARGET_LINE = 9999
@@
-ANOTHER_TARGET = 1500
+ANOTHER_TARGET = 8888
@@
*** End Patch"""
            
            result = await apply_patch_file.ainvoke({"patch_text": patch_text})
            assert "success" in result.lower(), f"Failed: {result}"
            
            with open(large_file) as f:
                content = f.read()
            assert "TARGET_LINE = 9999" in content
            assert "ANOTHER_TARGET = 8888" in content
        finally:
            os.unlink(large_file)

    @pytest.mark.asyncio
    async def test_patch_with_file_creation_deletion_chain(self):
        """
        Complex chain: Create temp file, use it, delete it.
        
        Simulates migration workflow.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            old_module = os.path.join(tmpdir, "old_module.py")
            new_module = os.path.join(tmpdir, "new_module.py")
            
            # Create old module
            with open(old_module, 'w') as f:
                f.write("# Old implementation\ndef func():\n    return 1\n")
            
            patch_text = f"""*** Begin Patch
*** Add File: {new_module}
+# New implementation
+def func():
+    return 2
*** Delete File: {old_module}
*** End Patch"""
            
            result = await apply_patch_file.ainvoke({"patch_text": patch_text})
            assert "success" in result.lower(), f"Failed: {result}"
            
            assert not os.path.exists(old_module), "Old module should be deleted"
            assert os.path.exists(new_module), "New module should exist"
            
            with open(new_module) as f:
                assert "return 2" in f.read()
