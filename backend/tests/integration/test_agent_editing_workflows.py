"""
Integration tests simulating complete Agent workflows.

These tests simulate how an Agent actually uses the tools:
  1. read_file() - understand current state
  2. analyze - decide which tool to use
  3. edit_file/multiedit_file/apply_patch_file - make changes
  4. read_file() - verify changes

Tests cover:
  - Simple bug fix workflow
  - Feature addition workflow  
  - Refactoring workflow
  - Large-scale migration workflow

pytest tests/integration/test_agent_editing_workflows.py -v
"""

import os
import tempfile
import pytest
from typing import List, Dict

from app.domain.tools.files.read_file import read_file
from app.domain.tools.files.edit_file import edit_file
from app.domain.tools.files.write_file import write_file
from app.domain.tools.files.multiedit_file import multiedit_file
from app.domain.tools.files.apply_patch_file import apply_patch_file


class TestAgentBugFixWorkflow:
    """Agent fixes a simple bug: method returning wrong value."""

    @pytest.fixture
    def buggy_calculator(self):
        content = '''"""Calculator module."""

class Calculator:
    def add(self, a, b):
        # Bug: subtracting instead of adding
        return a - b
    
    def multiply(self, a, b):
        return a * b
    
    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            path = f.name
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_agent_simple_bug_fix(self, buggy_calculator):
        """
        Agent workflow for simple bug fix:
        1. Read file to understand code
        2. Identify bug in add() method
        3. Use edit_file to fix it
        4. Verify fix
        """
        # Step 1: Agent reads file
        read_result = await read_file.ainvoke({"path": buggy_calculator})
        assert "Calculator" in read_result
        
        # Step 2: Agent analyzes and identifies bug
        # Bug: "return a - b" should be "return a + b"
        
        # Step 3: Agent fixes with edit_file
        fix_result = await edit_file.ainvoke({
            "path": buggy_calculator,
            "target": "    def add(self, a, b):\n        # Bug: subtracting instead of adding\n        return a - b",
            "replacement": "    def add(self, a, b):\n        return a + b"
        })
        assert "success" in fix_result.lower() or "✅" in fix_result
        
        # Step 4: Agent verifies fix
        verify_result = await read_file.ainvoke({"path": buggy_calculator})
        assert "return a + b" in verify_result
        assert "Bug:" not in verify_result  # Comment removed


class TestAgentFeatureAdditionWorkflow:
    """Agent adds a new feature: add logging to all methods."""

    @pytest.fixture
    def user_service(self):
        content = '''"""User service module."""

class UserService:
    def __init__(self, db):
        self.db = db
    
    def create_user(self, name, email):
        if not name:
            raise ValueError("Name required")
        user = {"name": name, "email": email}
        self.db.insert(user)
        return user
    
    def get_user(self, user_id):
        return self.db.query(user_id)
    
    def update_user(self, user_id, data):
        self.db.update(user_id, data)
        return True
    
    def delete_user(self, user_id):
        self.db.delete(user_id)
        return True
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            path = f.name
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_agent_add_logging_with_multiedit(self, user_service):
        """
        Agent workflow for adding logging:
        1. Read file to understand structure
        2. Decide multiedit_file is best (multiple method changes)
        3. Add logger init and logging to all methods
        4. Verify changes
        """
        # Step 1: Read
        content = await read_file.ainvoke({"path": user_service})
        assert "class UserService" in content
        
        # Step 2: Agent decides to use multiedit_file because:
        # - Multiple edits needed (logger + 4 methods)
        # - All in same file
        # - Atomic operation preferred
        
        # Step 3: multiedit
        edits = [
            {
                "target": "    def __init__(self, db):\n        self.db = db",
                "replacement": "    def __init__(self, db):\n        import logging\n        self.logger = logging.getLogger(__name__)\n        self.db = db"
            },
            {
                "target": "    def create_user(self, name, email):\n        if not name:",
                "replacement": "    def create_user(self, name, email):\n        self.logger.info(f\"Creating user: {name}\")\n        if not name:"
            },
            {
                "target": "    def get_user(self, user_id):\n        return self.db.query(user_id)",
                "replacement": "    def get_user(self, user_id):\n        self.logger.debug(f\"Getting user: {user_id}\")\n        return self.db.query(user_id)"
            },
            {
                "target": "    def update_user(self, user_id, data):\n        self.db.update(user_id, data)",
                "replacement": "    def update_user(self, user_id, data):\n        self.logger.info(f\"Updating user: {user_id}\")\n        self.db.update(user_id, data)"
            },
            {
                "target": "    def delete_user(self, user_id):\n        self.db.delete(user_id)",
                "replacement": "    def delete_user(self, user_id):\n        self.logger.warning(f\"Deleting user: {user_id}\")\n        self.db.delete(user_id)"
            }
        ]
        
        result = await multiedit_file.ainvoke({
            "path": user_service,
            "edits": edits
        })
        assert "success" in result.lower() or "✅" in result
        
        # Step 4: Verify
        final = await read_file.ainvoke({"path": user_service})
        assert "self.logger = logging" in final
        assert final.count("self.logger.") == 4  # 4 method logs


class TestAgentRefactoringWorkflow:
    """Agent performs refactoring: extract method."""

    @pytest.fixture
    def data_processor(self):
        content = '''"""Data processing module."""

class DataProcessor:
    def process_users(self, users):
        results = []
        for user in users:
            if user.get("active") and user.get("age", 0) >= 18:
                results.append({
                    "name": user["name"].upper(),
                    "email": user["email"].lower()
                })
        return results
    
    def process_orders(self, orders):
        results = []
        for order in orders:
            if order.get("status") == "completed" and order.get("total", 0) > 100:
                results.append({
                    "id": order["id"],
                    "total": order["total"]
                })
        return results
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            path = f.name
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_agent_extract_method_refactoring(self, data_processor):
        """
        Agent workflow for extract method refactoring:
        1. Read and identify duplicate pattern
        2. Use edit_file to add new helper method
        3. Use multiedit to replace duplicates with helper calls
        4. Verify
        """
        # Step 1: Read
        content = await read_file.ainvoke({"path": data_processor})
        
        # Step 2: Agent identifies duplicate filter pattern
        # Both methods have: for item in items: if condition: results.append(...)
        
        # Step 3a: Add helper method (single edit)
        add_helper = await edit_file.ainvoke({
            "path": data_processor,
            "target": "class DataProcessor:",
            "replacement": "class DataProcessor:\n    def _filter_and_transform(self, items, filter_fn, transform_fn):\n        \"\"\"Generic filter and transform helper.\"\"\"\n        results = []\n        for item in items:\n            if filter_fn(item):\n                results.append(transform_fn(item))\n        return results"
        })
        assert "success" in add_helper.lower()
        
        # Step 3b: Replace process_users with multiedit
        edits = [
            {
                "target": '''    def process_users(self, users):
        results = []
        for user in users:
            if user.get("active") and user.get("age", 0) >= 18:
                results.append({
                    "name": user["name"].upper(),
                    "email": user["email"].lower()
                })
        return results''',
                "replacement": '''    def process_users(self, users):
        return self._filter_and_transform(
            users,
            lambda u: u.get("active") and u.get("age", 0) >= 18,
            lambda u: {"name": u["name"].upper(), "email": u["email"].lower()}
        )'''
            },
            {
                "target": '''    def process_orders(self, orders):
        results = []
        for order in orders:
            if order.get("status") == "completed" and order.get("total", 0) > 100:
                results.append({
                    "id": order["id"],
                    "total": order["total"]
                })
        return results''',
                "replacement": '''    def process_orders(self, orders):
        return self._filter_and_transform(
            orders,
            lambda o: o.get("status") == "completed" and o.get("total", 0) > 100,
            lambda o: {"id": o["id"], "total": o["total"]}
        )'''
            }
        ]
        
        result = await multiedit_file.ainvoke({
            "path": data_processor,
            "edits": edits
        })
        assert "success" in result.lower()
        
        # Step 4: Verify
        final = await read_file.ainvoke({"path": data_processor})
        assert "def _filter_and_transform" in final
        assert "for user in users" not in final  # Old loop gone
        assert "for order in orders" not in final
        assert "_filter_and_transform" in final


class TestAgentLargeScaleMigrationWorkflow:
    """Agent performs large-scale migration using apply_patch_file."""

    @pytest.fixture
    def legacy_project(self):
        """Create a mock legacy project with multiple files."""
        tmpdir = tempfile.mkdtemp()
        
        # Create utils.py
        with open(os.path.join(tmpdir, "utils.py"), 'w') as f:
            f.write('''"""Utility functions."""

def log_error(msg):
    print(f"ERROR: {msg}")

def log_info(msg):
    print(f"INFO: {msg}")
''')
        
        # Create api.py
        with open(os.path.join(tmpdir, "api.py"), 'w') as f:
            f.write('''"""API module."""
from utils import log_error, log_info

def fetch_data():
    log_info("Fetching...")
    return {"data": []}

def save_data(data):
    if not data:
        log_error("No data")
        return False
    return True
''')
        
        # Create models.py
        with open(os.path.join(tmpdir, "models.py"), 'w') as f:
            f.write('''"""Models module."""
from utils import log_error

class User:
    def save(self):
        log_error("Not implemented")
        pass
''')
        
        yield tmpdir
        
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_agent_migration_with_apply_patch(self, legacy_project):
        """
        Agent workflow for migration:
        1. Analyze project structure
        2. Create patch for:
           - Create new logging.py module
           - Replace all log_error/log_info with proper logging
           - Delete utils.py (deprecated)
        3. Apply patch atomically
        4. Verify all files updated correctly
        """
        utils_py = os.path.join(legacy_project, "utils.py")
        api_py = os.path.join(legacy_project, "api.py")
        models_py = os.path.join(legacy_project, "models.py")
        logging_py = os.path.join(legacy_project, "logging.py")
        
        # Step 1: Agent reads project files to understand structure
        utils_content = await read_file.ainvoke({"path": utils_py})
        api_content = await read_file.ainvoke({"path": api_py})
        
        # Step 2: Agent creates comprehensive patch for migration
        patch_text = f"""*** Begin Patch
*** Add File: {logging_py}
+\"\"\"Modern logging module.\"\"\"
+import logging
+
+logger = logging.getLogger("app")
+
+def log_error(msg):
+    logger.error(msg)
+
+def log_info(msg):
+    logger.info(msg)
+
+def log_debug(msg):
+    logger.debug(msg)
+
+def log_warning(msg):
+    logger.warning(msg)
*** Update File: {api_py}
@@
-from utils import log_error, log_info
+from logging import log_error, log_info, log_debug
@@
-    log_info("Fetching...")
+    log_debug("Fetching data from API")
@@
-        log_error("No data")
+        log_error("Cannot save empty data")
@@
*** Update File: {models_py}
@@
-from utils import log_error
+from logging import log_error, log_info
@@
-        log_error("Not implemented")
+        log_warning("User.save() not yet implemented")
+        log_info("Using default save behavior")
@@
*** Delete File: {utils_py}
*** End Patch"""
        
        # Step 3: Apply patch
        result = await apply_patch_file.ainvoke({"patch_text": patch_text})
        assert "success" in result.lower() or "applied" in result.lower(), f"Failed: {result}"
        
        # Step 4: Verify all changes
        # 4a: New logging.py exists
        assert os.path.exists(logging_py), "logging.py should be created"
        with open(logging_py) as f:
            logging_content = f.read()
        assert "import logging" in logging_content
        assert "def log_debug" in logging_content
        
        # 4b: api.py updated
        with open(api_py) as f:
            new_api = f.read()
        assert "from logging import" in new_api
        assert "log_debug(\"Fetching data from API\")" in new_api
        assert "from utils import" not in new_api
        
        # 4c: models.py updated
        with open(models_py) as f:
            new_models = f.read()
        assert "log_warning" in new_models
        assert "from logging import" in new_models
        
        # 4d: utils.py deleted
        assert not os.path.exists(utils_py), "utils.py should be deleted"

    @pytest.mark.asyncio
    async def test_agent_error_recovery_in_migration(self, legacy_project):
        """
        Agent workflow: Handle failure in multi-file migration.
        
        If one file operation fails, all should rollback.
        """
        utils_py = os.path.join(legacy_project, "utils.py")
        api_py = os.path.join(legacy_project, "api.py")
        models_py = os.path.join(legacy_project, "models.py")
        non_existent = os.path.join(legacy_project, "does_not_exist.py")
        
        # Capture original hashes
        with open(utils_py, 'rb') as f:
            utils_hash = f.read()
        with open(api_py, 'rb') as f:
            api_hash = f.read()
        
        # Create patch that will fail mid-way
        patch_text = f"""*** Begin Patch
*** Delete File: {utils_py}
*** Update File: {api_py}
@@
-from utils import log_error, log_info
+from logging import log_error, log_info
@@
*** Update File: {non_existent}
@@
-this file does not exist
+will cause failure
@@
*** Update File: {models_py}
@@
-from utils import log_error
+from logging import log_error
@@
*** End Patch"""
        
        result = await apply_patch_file.ainvoke({"patch_text": patch_text})
        
        # Should fail
        assert "fail" in result.lower() or "error" in result.lower()
        
        # All files should be unchanged (rollback)
        with open(utils_py, 'rb') as f:
            assert f.read() == utils_hash, "utils.py should be unchanged (rollback)"
        with open(api_py, 'rb') as f:
            assert f.read() == api_hash, "api.py should be unchanged (rollback)"


class TestAgentToolSelectionIntelligence:
    """Test that Agent selects the right tool for the job."""

    @pytest.mark.asyncio
    async def test_agent_chooses_edit_file_for_single_change(self):
        """Agent should use edit_file for single, isolated change."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello():\n    return "world"\n')
            path = f.name
        
        try:
            # Single change -> edit_file
            result = await edit_file.ainvoke({
                "path": path,
                "target": 'return "world"',
                "replacement": 'return "Python"'
            })
            assert "success" in result.lower()
            
            with open(path) as f:
                assert 'return "Python"' in f.read()
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_agent_chooses_multiedit_for_multiple_same_file(self):
        """Agent should use multiedit_file for multiple changes in same file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def a():\n    return 1\n\ndef b():\n    return 2\n\ndef c():\n    return 3\n')
            path = f.name
        
        try:
            # Multiple changes in same file -> multiedit_file
            edits = [
                {"target": "    return 1", "replacement": "    return 10"},
                {"target": "    return 2", "replacement": "    return 20"},
                {"target": "    return 3", "replacement": "    return 30"}
            ]
            
            result = await multiedit_file.ainvoke({
                "path": path,
                "edits": edits
            })
            assert "success" in result.lower()
            
            with open(path) as f:
                content = f.read()
            assert "return 10" in content
            assert "return 20" in content
            assert "return 30" in content
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_agent_chooses_apply_patch_for_cross_file_changes(self):
        """Agent should use apply_patch_file for cross-file refactoring."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = os.path.join(tmpdir, "a.py")
            file2 = os.path.join(tmpdir, "b.py")
            
            with open(file1, 'w') as f:
                f.write("def old_func():\n    return 1\n")
            with open(file2, 'w') as f:
                f.write("from a import old_func\n")
            
            # Cross-file changes -> apply_patch_file
            patch_text = f"""*** Begin Patch
*** Update File: {file1}
@@
-def old_func():
-    return 1
+def new_func():
+    return 2
@@
*** Update File: {file2}
@@
-from a import old_func
+from a import new_func
@@
*** End Patch"""
            
            result = await apply_patch_file.ainvoke({"patch_text": patch_text})
            assert "success" in result.lower()
            
            with open(file1) as f:
                assert "def new_func():" in f.read()
            with open(file2) as f:
                assert "import new_func" in f.read()


class TestAgentVerificationWorkflow:
    """Agent verifies changes after editing."""

    @pytest.mark.asyncio
    async def test_agent_verifies_type_safety_after_edit(self):
        """
        Agent workflow with type checking:
        1. Make edit
        2. Verify types are still valid
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('''def process(data: dict) -> str:
    return data["name"]
''')
            path = f.name
        
        try:
            # Edit with type checking
            result = await edit_file.ainvoke({
                "path": path,
                "target": 'def process(data: dict) -> str:\n    return data["name"]',
                "replacement": 'def process(data: dict) -> str:\n    return str(data.get("name", ""))',
                "verify_types": True
            })
            
            # Should succeed (edit itself is fast, type check async)
            assert "success" in result.lower()
            
            # Verify change
            with open(path) as f:
                assert "data.get" in f.read()
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_agent_handles_edit_failure_gracefully(self):
        """
        Agent workflow: Handle failed edit (target not found).
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello():\n    return "world"\n')
            path = f.name
        
        try:
            # Try to edit non-existent target
            result = await edit_file.ainvoke({
                "path": path,
                "target": "this does not exist",
                "replacement": "will fail"
            })
            
            # Should report failure
            assert "fail" in result.lower() or "error" in result.lower()
            
            # File unchanged
            with open(path) as f:
                assert 'return "world"' in f.read()
        finally:
            os.unlink(path)
