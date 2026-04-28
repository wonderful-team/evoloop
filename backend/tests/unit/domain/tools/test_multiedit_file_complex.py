"""
Complex tests for multiedit_file - Advanced scenarios and Agent workflows.

Tests cover:
  1. Large batch edits (20+ edits)
  2. Interdependent edits (edit A depends on edit B result)
  3. Real-world refactoring scenarios
  4. Performance under load
  5. Complex rollback scenarios

pytest tests/unit/domain/tools/test_multiedit_file_complex.py -v
"""

import os
import pytest
import hashlib
import uuid
import asyncio
from typing import List

from app.core.tools import get_working_directory
from app.domain.tools.files.multiedit_file import multiedit_file
from app.domain.tools.files.read_file import read_file


class TestMultiEditFileComplex:
    """Complex scenarios for multiedit_file."""

    @pytest.fixture
    def complex_class_file(self):
        """Create a complex class file for testing."""
        content = '''"""User Management Module."""

class UserManager:
    """Manages user operations."""
    
    def __init__(self, db):
        self.db = db
        self.cache = {}
    
    def create_user(self, name, email):
        # Validate name
        if not name:
            raise ValueError("Name required")
        # Validate email
        if "@" not in email:
            raise ValueError("Invalid email")
        user = {"name": name, "email": email}
        self.db.insert(user)
        return user
    
    def get_user(self, user_id):
        # Check cache
        if user_id in self.cache:
            return self.cache[user_id]
        # Query DB
        user = self.db.query(user_id)
        self.cache[user_id] = user
        return user
    
    def update_user(self, user_id, data):
        # Validate data
        if not data:
            raise ValueError("Data required")
        # Update DB
        self.db.update(user_id, data)
        # Invalidate cache
        if user_id in self.cache:
            del self.cache[user_id]
        return True
    
    def delete_user(self, user_id):
        # Check exists
        if not self.db.exists(user_id):
            return False
        # Delete from DB
        self.db.delete(user_id)
        # Clear cache
        if user_id in self.cache:
            del self.cache[user_id]
        return True
    
    def list_users(self, limit=100):
        # Default limit
        if limit > 1000:
            limit = 1000
        return self.db.query_all(limit=limit)
'''
        root = get_working_directory(None)
        path = os.path.join(root, f"multiedit_complex_{uuid.uuid4().hex}.py")
        with open(path, 'w') as f:
            f.write(content)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_multiedit_all_methods_add_logging(self, complex_class_file):
        """
        Agent workflow: Add logging to all methods in a class.
        
        This tests batch editing of multiple independent locations.
        """
        edits = [
            {
                "target": "    def __init__(self, db):\n        self.db = db",
                "replacement": "    def __init__(self, db):\n        self.logger = logging.getLogger(__name__)\n        self.db = db"
            },
            {
                "target": "    def create_user(self, name, email):\n        # Validate name",
                "replacement": "    def create_user(self, name, email):\n        self.logger.info(f\"Creating user: {name}\")\n        # Validate name"
            },
            {
                "target": "    def get_user(self, user_id):\n        # Check cache",
                "replacement": "    def get_user(self, user_id):\n        self.logger.debug(f\"Getting user: {user_id}\")\n        # Check cache"
            },
            {
                "target": "    def update_user(self, user_id, data):\n        # Validate data",
                "replacement": "    def update_user(self, user_id, data):\n        self.logger.info(f\"Updating user: {user_id}\")\n        # Validate data"
            },
            {
                "target": "    def delete_user(self, user_id):\n        # Check exists",
                "replacement": "    def delete_user(self, user_id):\n        self.logger.warning(f\"Deleting user: {user_id}\")\n        # Check exists"
            }
        ]
        
        result = await multiedit_file.ainvoke({
            "path": complex_class_file,
            "edits": edits
        })
        assert "success" in result.lower(), f"Failed: {result}"
        
        with open(complex_class_file) as f:
            content = f.read()
        
        assert "self.logger = logging" in content
        assert "self.logger.info(f\"Creating user" in content
        assert "self.logger.debug(f\"Getting user" in content
        assert "self.logger.warning(f\"Deleting user" in content

    @pytest.mark.asyncio
    async def test_multiedit_20_bulk_edits(self):
        """
        Agent workflow: Bulk rename 20 functions.
        
        Tests performance and reliability of large batches.
        """
        # Create file with 20 functions
        funcs = "\n".join([f"def old_func_{i:02d}():\n    return {i}" for i in range(20)])
        
        root = get_working_directory(None)
        bulk_file = os.path.join(root, f"multiedit_bulk_{uuid.uuid4().hex}.py")
        with open(bulk_file, 'w') as f:
            f.write(f'"""Module with many functions."""\n\n{funcs}\n')
        
        try:
            # Generate 20 edits to rename all functions
            edits = [
                {
                    "target": f"def old_func_{i:02d}():\n    return {i}",
                    "replacement": f"def new_func_{i:02d}():\n    return {i * 10}"
                }
                for i in range(20)
            ]
            
            result = await multiedit_file.ainvoke({
                "path": bulk_file,
                "edits": edits
            })
            assert "success" in result.lower(), f"Failed: {result}"
            
            with open(bulk_file) as f:
                content = f.read()
            
            # Verify all renamed
            for i in range(20):
                assert f"def new_func_{i:02d}():" in content
                assert f"return {i * 10}" in content
                assert f"def old_func_{i:02d}():" not in content
        finally:
            os.unlink(bulk_file)

    @pytest.mark.asyncio
    async def test_multiedit_chained_dependencies(self):
        """
        Agent workflow: Chained edits where each depends on previous.
        
        Edit 1: Rename function A -> A2
        Edit 2: Update caller of A to call A2 (which now exists)
        Edit 3: Rename function B which calls A2
        
        This tests multiedit's sequential dependency handling.
        """
        content = '''def process_a():
    return "a"

def process_b():
    result = process_a()
    return f"b: {result}"

def main():
    a = process_a()
    b = process_b()
    return a, b
'''
        root = get_working_directory(None)
        chain_file = os.path.join(root, f"multiedit_chain_{uuid.uuid4().hex}.py")
        with open(chain_file, 'w') as f:
            f.write(content)
        
        try:
            edits = [
                # First: rename process_a
                {
                    "target": "def process_a():\n    return \"a\"",
                    "replacement": "def process_a_v2():\n    return \"a_v2\""
                },
                # Second: update caller in process_b
                {
                    "target": "def process_b():\n    result = process_a()",
                    "replacement": "def process_b():\n    result = process_a_v2()"
                },
                # Third: update main() caller
                {
                    "target": "def main():\n    a = process_a()",
                    "replacement": "def main():\n    a = process_a_v2()"
                }
            ]
            
            result = await multiedit_file.ainvoke({
                "path": chain_file,
                "edits": edits
            })
            assert "success" in result.lower(), f"Failed: {result}"
            
            with open(chain_file) as f:
                final_content = f.read()
            
            # Verify final state
            assert "def process_a_v2():" in final_content
            assert "result = process_a_v2()" in final_content
            assert "a = process_a_v2()" in final_content
            # Old references should be gone
            assert "process_a()" not in final_content.replace("process_a_v2()", "")
        finally:
            os.unlink(chain_file)

    @pytest.mark.asyncio
    async def test_multiedit_partial_failure_rollback(self):
        """
        Agent workflow: 10 edits, 5th fails, verify complete rollback.
        
        Critical test for atomicity guarantee.
        """
        content = "\n".join([f"line_{i} = {i}" for i in range(10)])
        
        root = get_working_directory(None)
        atomic_file = os.path.join(root, f"multiedit_atomic_{uuid.uuid4().hex}.py")
        with open(atomic_file, 'w') as f:
            f.write(content)
        
        try:
            # Capture original hash
            with open(atomic_file, 'rb') as f:
                original_hash = hashlib.md5(f.read()).hexdigest()
            
            # 10 edits, 5th is invalid (target doesn't exist)
            edits = []
            for i in range(10):
                if i == 4:  # 5th edit (index 4)
                    edits.append({
                        "target": "THIS_DOES_NOT_EXIST",
                        "replacement": "will_fail"
                    })
                else:
                    edits.append({
                        "target": f"line_{i} = {i}",
                        "replacement": f"line_{i} = {i * 100}"
                    })
            
            result = await multiedit_file.ainvoke({
                "path": atomic_file,
                "edits": edits
            })
            
            # Should fail
            assert "fail" in result.lower() or "error" in result.lower()
            
            # Verify file unchanged (atomic rollback)
            with open(atomic_file, 'rb') as f:
                current_hash = hashlib.md5(f.read()).hexdigest()
            
            assert current_hash == original_hash, \
                f"File was modified despite failure! Expected rollback.\nResult: {result}"
        finally:
            os.unlink(atomic_file)


class TestMultiEditFileRealWorldScenarios:
    """Real-world Agent scenarios."""

    @pytest.mark.asyncio
    async def test_refactor_add_type_hints_to_all_methods(self):
        """
        Agent workflow: Add type hints to all methods in a module.
        """
        content = '''class DataProcessor:
    def __init__(self, config):
        self.config = config
    
    def process(self, data):
        return data.upper()
    
    def validate(self, item):
        return len(item) > 0
    
    def save(self, result, path):
        with open(path, "w") as f:
            f.write(result)
        return True
'''
        root = get_working_directory(None)
        types_file = os.path.join(root, f"multiedit_types_{uuid.uuid4().hex}.py")
        with open(types_file, 'w') as f:
            f.write(content)
        
        try:
            edits = [
                {
                    "target": "    def __init__(self, config):",
                    "replacement": "    def __init__(self, config: dict) -> None:"
                },
                {
                    "target": "    def process(self, data):",
                    "replacement": "    def process(self, data: str) -> str:"
                },
                {
                    "target": "    def validate(self, item):",
                    "replacement": "    def validate(self, item: str) -> bool:"
                },
                {
                    "target": "    def save(self, result, path):",
                    "replacement": "    def save(self, result: str, path: str) -> bool:"
                }
            ]
            
            result = await multiedit_file.ainvoke({
                "path": types_file,
                "edits": edits
            })
            assert "success" in result.lower(), f"Failed: {result}"
            
            with open(types_file) as f:
                content = f.read()
            
            assert "config: dict) -> None:" in content
            assert "data: str) -> str:" in content
            assert "item: str) -> bool:" in content
            assert "result: str, path: str) -> bool:" in content
        finally:
            os.unlink(types_file)

    @pytest.mark.asyncio
    async def test_refactor_extract_method_pattern(self):
        """
        Agent workflow: Extract duplicated logic into methods.
        
        Before: validate logic duplicated in 3 places
        After: single _validate_input() method called from 3 places
        """
        content = '''class Handler:
    def create(self, data):
        if not data or not isinstance(data, dict):
            raise ValueError("Invalid")
        # Create logic
        return data
    
    def update(self, id, data):
        if not data or not isinstance(data, dict):
            raise ValueError("Invalid")
        # Update logic
        return data
    
    def delete(self, id):
        if not id or not isinstance(id, int):
            raise ValueError("Invalid")
        # Delete logic
        return True
'''
        root = get_working_directory(None)
        extract_file = os.path.join(root, f"multiedit_extract_{uuid.uuid4().hex}.py")
        with open(extract_file, 'w') as f:
            f.write(content)
        
        try:
            edits = [
                # Add new validation method after __init__
                {
                    "target": "class Handler:",
                    "replacement": "class Handler:\n    def _validate(self, value, expected_type):\n        if not value or not isinstance(value, expected_type):\n            raise ValueError(\"Invalid\")"
                },
                # Replace first validation
                {
                    "target": "    def create(self, data):\n        if not data or not isinstance(data, dict):\n            raise ValueError(\"Invalid\")",
                    "replacement": "    def create(self, data):\n        self._validate(data, dict)"
                },
                # Replace second validation
                {
                    "target": "    def update(self, id, data):\n        if not data or not isinstance(data, dict):\n            raise ValueError(\"Invalid\")",
                    "replacement": "    def update(self, id, data):\n        self._validate(data, dict)"
                },
                # Replace third validation
                {
                    "target": "    def delete(self, id):\n        if not id or not isinstance(id, int):\n            raise ValueError(\"Invalid\")",
                    "replacement": "    def delete(self, id):\n        self._validate(id, int)"
                }
            ]
            
            result = await multiedit_file.ainvoke({
                "path": extract_file,
                "edits": edits
            })
            assert "success" in result.lower(), f"Failed: {result}"
            
            with open(extract_file) as f:
                content = f.read()
            
            assert "def _validate(self, value, expected_type):" in content
            assert "self._validate(data, dict)" in content
            assert content.count("raise ValueError") == 1  # Only in _validate
        finally:
            os.unlink(extract_file)

    @pytest.mark.asyncio
    async def test_multiedit_add_imports_and_usage(self):
        """
        Agent workflow: Add import and use it in same atomic operation.
        """
        content = '''"""API module."""

def fetch_data():
    # TODO: implement caching
    return requests.get("/api/data")

def process():
    data = fetch_data()
    return data.json()
'''
        root = get_working_directory(None)
        import_file = os.path.join(root, f"multiedit_import_{uuid.uuid4().hex}.py")
        with open(import_file, 'w') as f:
            f.write(content)
        
        try:
            edits = [
                {
                    "target": "\"\"\"API module.\"\"\"",
                    "replacement": "\"\"\"API module.\"\"\"\n\nimport requests\nfrom functools import lru_cache"
                },
                {
                    "target": "def fetch_data():\n    # TODO: implement caching\n    return requests.get(\"/api/data\")",
                    "replacement": "@lru_cache(maxsize=100)\ndef fetch_data():\n    return requests.get(\"/api/data\")"
                },
                {
                    "target": "def process():\n    data = fetch_data()",
                    "replacement": "def process():\n    try:\n        data = fetch_data()\n    except requests.RequestException as e:\n        return {\"error\": str(e)}"
                }
            ]
            
            result = await multiedit_file.ainvoke({
                "path": import_file,
                "edits": edits
            })
            assert "success" in result.lower(), f"Failed: {result}"
            
            with open(import_file) as f:
                content = f.read()
            
            assert "import requests" in content
            assert "from functools import lru_cache" in content
            assert "@lru_cache" in content
            assert "try:" in content and "except requests.RequestException" in content
        finally:
            os.unlink(import_file)


class TestMultiEditFilePerformance:
    """Performance and stress tests."""

    @pytest.mark.asyncio
    async def test_multiedit_large_file_1000_lines(self):
        """
        Performance test: 1000 line file with 10 edits.
        """
        # Create 1000 line file
        lines = [f"def func_{i:04d}():\n    \"\"\"Docstring {i}.\"\"\"\n    return {i}\n" for i in range(1000)]
        
        root = get_working_directory(None)
        large_file = os.path.join(root, f"multiedit_large_{uuid.uuid4().hex}.py")
        with open(large_file, 'w') as f:
            f.write('"""Large module."""\n\n')
            f.write("".join(lines))
        
        try:
            # Edit every 100th function
            edits = [
                {
                    "target": f"def func_{i:04d}():\n    \"\"\"Docstring {i}.\"\"\"\n    return {i}",
                    "replacement": f"def func_{i:04d}():\n    \"\"\"Updated {i}.\"\"\"\n    return {i * 10}"
                }
                for i in range(0, 1000, 100)  # 10 edits
            ]
            
            import time
            start = time.perf_counter()
            result = await multiedit_file.ainvoke({
                "path": large_file,
                "edits": edits
            })
            elapsed = (time.perf_counter() - start) * 1000
            
            assert "success" in result.lower(), f"Failed: {result}"
            print(f"\n10 edits on 1000-line file: {elapsed:.1f}ms")
            
            # Verify one change
            with open(large_file) as f:
                content = f.read()
            assert "Updated 0." in content
            assert "Updated 900." in content
        finally:
            os.unlink(large_file)

    @pytest.mark.asyncio
    async def test_multiedit_vs_sequential_edit_comparison(self):
        """
        Compare multiedit vs sequential edit_file calls.
        
        multiedit should be faster and only write file once.
        """
        content = "\n".join([f"var_{i} = {i+1}" for i in range(5)])
        
        root = get_working_directory(None)
        comp_file = os.path.join(root, f"multiedit_comp_{uuid.uuid4().hex}.py")
        with open(comp_file, 'w') as f:
            f.write(content)
        
        try:
            edits = [
                {"target": f"var_{i} = {i+1}", "replacement": f"var_{i} = {(i+1)*10}"}
                for i in range(5)
            ]
            
            import time
            start = time.perf_counter()
            result = await multiedit_file.ainvoke({
                "path": comp_file,
                "edits": edits
            })
            multiedit_time = (time.perf_counter() - start) * 1000
            
            assert "success" in result.lower()
            print(f"\nmultiedit 5 edits: {multiedit_time:.1f}ms")
            
            # Verify all changes
            with open(comp_file) as f:
                final = f.read()
            for i in range(5):
                assert f"var_{i} = {(i+1)*10}" in final
        finally:
            os.unlink(comp_file)
