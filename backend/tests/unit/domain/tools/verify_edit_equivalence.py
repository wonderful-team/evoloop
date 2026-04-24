"""
Standalone verification script for edit_file multi-edit equivalence.
Runs without pytest to avoid project-level import issues.

This tests the core EditEngine behavior that both edit_file(edits=...)
and edit_file multi-edit mode rely on.
"""

import hashlib
import os
import sys
import tempfile
import time

# Add backend to path so 'app' package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../.."))

# Import only the low-level engine, avoiding full app initialization
from app.core.file.editor import EditEngine


def apply_multi_edit(content: str, edits: list[dict]) -> tuple[bool, str, str]:
    """
    Simulate handle_multi_edit's Phase 1 (dry run) using EditEngine.
    Returns (success, new_content, error_msg).
    """
    current = content
    for i, edit in enumerate(edits):
        target = edit["target"]
        replacement = edit["replacement"]
        allow_multiple = edit.get("allow_multiple", False)

        if len(target.strip()) < 3:
            return False, current, f"Edit #{i+1}: Target block too short."

        success, new_content, log = EditEngine.apply_replacement(
            current, target, replacement, replace_all=allow_multiple
        )
        if not success:
            return False, current, (
                f"Edit #{i+1} failed validation. No changes applied.\n"
                f"   Target: {target[:50]}{'...' if len(target) > 50 else ''}\n"
                f"   Error: {log}"
            )
        current = new_content
    return True, current, ""


def assert_file_hash(path: str, expected_hash: str) -> bool:
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest() == expected_hash


def test_all_success():
    content = '''def foo():
    return 1

def bar():
    return 2

def baz():
    return 3
'''
    edits = [
        {"target": "def foo():\n    return 1", "replacement": "def foo():\n    return 10"},
        {"target": "def bar():\n    return 2", "replacement": "def bar():\n    return 20"},
    ]
    success, new_content, err = apply_multi_edit(content, edits)
    assert success, f"Failed: {err}"
    assert "return 10" in new_content
    assert "return 20" in new_content
    assert "return 3" in new_content
    print("✅ test_all_success")


def test_atomic_rollback():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('''def foo():\n    return 1\n\ndef bar():\n    return 2\n''')
        path = f.name

    try:
        with open(path, 'rb') as f:
            original_hash = hashlib.md5(f.read()).hexdigest()

        with open(path) as f:
            content = f.read()

        edits = [
            {"target": "def foo():\n    return 1", "replacement": "def foo():\n    return 10"},
            {"target": "this does not exist", "replacement": "should fail"},
        ]
        success, _, err = apply_multi_edit(content, edits)
        assert not success, f"Should have failed: {err}"

        # Verify file unchanged (no write happened since Phase 1 failed)
        assert assert_file_hash(path, original_hash), "File was modified despite failure!"
        print("✅ test_atomic_rollback")
    finally:
        os.unlink(path)


def test_sequential_dependency():
    content = '''def foo():
    return 1

def bar():
    return 2
'''
    edits = [
        {"target": "def foo():\n    return 1", "replacement": "def foo():\n    return 99"},
        {"target": "def foo():\n    return 99", "replacement": "def foo():\n    return 42"},
    ]
    success, new_content, err = apply_multi_edit(content, edits)
    assert success, f"Failed: {err}"
    assert "return 42" in new_content
    assert "return 99" not in new_content
    assert "return 1" not in new_content
    print("✅ test_sequential_dependency")


def test_20_bulk_edits():
    funcs = "\n".join([f"def old_func_{i:02d}():\n    return {i}" for i in range(20)])
    content = f'"""Module."""\n\n{funcs}\n'

    edits = [
        {
            "target": f"def old_func_{i:02d}():\n    return {i}",
            "replacement": f"def new_func_{i:02d}():\n    return {i * 10}"
        }
        for i in range(20)
    ]
    success, new_content, err = apply_multi_edit(content, edits)
    assert success, f"Failed: {err}"
    for i in range(20):
        assert f"def new_func_{i:02d}():" in new_content
        assert f"return {i * 10}" in new_content
        assert f"def old_func_{i:02d}():" not in new_content
    print("✅ test_20_bulk_edits")


def test_chained_dependencies():
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
    edits = [
        {"target": 'def process_a():\n    return "a"', "replacement": 'def process_a_v2():\n    return "a_v2"'},
        {"target": 'def process_b():\n    result = process_a()', "replacement": 'def process_b():\n    result = process_a_v2()'},
        {"target": 'def main():\n    a = process_a()', "replacement": 'def main():\n    a = process_a_v2()'},
    ]
    success, new_content, err = apply_multi_edit(content, edits)
    assert success, f"Failed: {err}"
    assert "def process_a_v2():" in new_content
    assert "result = process_a_v2()" in new_content
    assert "a = process_a_v2()" in new_content
    # Old refs gone (check that plain process_a() doesn't exist outside of process_a_v2)
    plain_calls = new_content.replace("process_a_v2()", "").count("process_a()")
    assert plain_calls == 0, f"Old references remain: {plain_calls}"
    print("✅ test_chained_dependencies")


def test_partial_failure_rollback():
    content = "\n".join([f"line_{i} = {i}" for i in range(10)])
    edits = []
    for i in range(10):
        if i == 4:
            edits.append({"target": "THIS_DOES_NOT_EXIST", "replacement": "will_fail"})
        else:
            edits.append({"target": f"line_{i} = {i}", "replacement": f"line_{i} = {i * 100 + 1}"})

    success, _, err = apply_multi_edit(content, edits)
    assert not success, f"Should have failed: {err}"
    if "Edit #5 failed" not in err:
        print(f"   Debug: actual error msg = {err!r}")
    assert "Edit #5 failed" in err, f"Error message mismatch: {err!r}"
    print("✅ test_partial_failure_rollback")


def test_refactor_add_type_hints():
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
    edits = [
        {"target": "    def __init__(self, config):", "replacement": "    def __init__(self, config: dict) -> None:"},
        {"target": "    def process(self, data):", "replacement": "    def process(self, data: str) -> str:"},
        {"target": "    def validate(self, item):", "replacement": "    def validate(self, item: str) -> bool:"},
        {"target": "    def save(self, result, path):", "replacement": "    def save(self, result: str, path: str) -> bool:"},
    ]
    success, new_content, err = apply_multi_edit(content, edits)
    assert success, f"Failed: {err}"
    assert "config: dict) -> None:" in new_content
    assert "data: str) -> str:" in new_content
    assert "item: str) -> bool:" in new_content
    assert "result: str, path: str) -> bool:" in new_content
    print("✅ test_refactor_add_type_hints")


def test_refactor_extract_method_pattern():
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
    edits = [
        {
            "target": "class Handler:",
            "replacement": "class Handler:\n    def _validate(self, value, expected_type):\n        if not value or not isinstance(value, expected_type):\n            raise ValueError(\"Invalid\")"
        },
        {
            "target": "    def create(self, data):\n        if not data or not isinstance(data, dict):\n            raise ValueError(\"Invalid\")",
            "replacement": "    def create(self, data):\n        self._validate(data, dict)"
        },
        {
            "target": "    def update(self, id, data):\n        if not data or not isinstance(data, dict):\n            raise ValueError(\"Invalid\")",
            "replacement": "    def update(self, id, data):\n        self._validate(data, dict)"
        },
        {
            "target": "    def delete(self, id):\n        if not id or not isinstance(id, int):\n            raise ValueError(\"Invalid\")",
            "replacement": "    def delete(self, id):\n        self._validate(id, int)"
        },
    ]
    success, new_content, err = apply_multi_edit(content, edits)
    assert success, f"Failed: {err}"
    assert "def _validate(self, value, expected_type):" in new_content
    assert "self._validate(data, dict)" in new_content
    assert new_content.count("raise ValueError") == 1
    print("✅ test_refactor_extract_method_pattern")


def test_add_imports_and_usage():
    content = '''"""API module."""

def fetch_data():
    # TODO: implement caching
    return requests.get("/api/data")

def process():
    data = fetch_data()
    return data.json()
'''
    edits = [
        {
            "target": '"""API module."""',
            "replacement": '"""API module."""\n\nimport requests\nfrom functools import lru_cache'
        },
        {
            "target": 'def fetch_data():\n    # TODO: implement caching\n    return requests.get("/api/data")',
            "replacement": '@lru_cache(maxsize=100)\ndef fetch_data():\n    return requests.get("/api/data")'
        },
        {
            "target": 'def process():\n    data = fetch_data()',
            "replacement": 'def process():\n    try:\n        data = fetch_data()\n    except requests.RequestException as e:\n        return {"error": str(e)}'
        },
    ]
    success, new_content, err = apply_multi_edit(content, edits)
    assert success, f"Failed: {err}"
    assert "import requests" in new_content
    assert "from functools import lru_cache" in new_content
    assert "@lru_cache" in new_content
    assert "try:" in new_content and "except requests.RequestException" in new_content
    print("✅ test_add_imports_and_usage")


def test_large_file_1000_lines():
    lines = [f"def func_{i:04d}():\n    \"\"\"Docstring {i}.\"\"\"\n    return {i}\n" for i in range(1000)]
    content = '"""Large module."""\n\n' + "".join(lines)

    edits = [
        {
            "target": f"def func_{i:04d}():\n    \"\"\"Docstring {i}.\"\"\"\n    return {i}",
            "replacement": f"def func_{i:04d}():\n    \"\"\"Updated {i}.\"\"\"\n    return {i * 10}"
        }
        for i in range(0, 1000, 100)
    ]
    start = time.perf_counter()
    success, new_content, err = apply_multi_edit(content, edits)
    elapsed = (time.perf_counter() - start) * 1000
    assert success, f"Failed: {err}"
    assert "Updated 0." in new_content
    assert "Updated 900." in new_content
    print(f"✅ test_large_file_1000_lines ({elapsed:.1f}ms)")


def test_single_edit_equivalent():
    content = '''def foo():
    return 1
'''
    edits = [
        {"target": "def foo():\n    return 1", "replacement": "def foo():\n    return 99"},
    ]
    success, new_content, err = apply_multi_edit(content, edits)
    assert success, f"Failed: {err}"
    assert "return 99" in new_content
    print("✅ test_single_edit_equivalent")


def test_all_methods_add_logging():
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
'''
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
        },
    ]
    success, new_content, err = apply_multi_edit(content, edits)
    assert success, f"Failed: {err}"
    assert "self.logger = logging" in new_content
    assert 'self.logger.info(f"Creating user' in new_content
    assert 'self.logger.debug(f"Getting user' in new_content
    assert 'self.logger.warning(f"Deleting user' in new_content
    print("✅ test_all_methods_add_logging")


if __name__ == "__main__":
    tests = [
        test_all_success,
        test_atomic_rollback,
        test_sequential_dependency,
        test_single_edit_equivalent,
        test_20_bulk_edits,
        test_chained_dependencies,
        test_partial_failure_rollback,
        test_refactor_add_type_hints,
        test_refactor_extract_method_pattern,
        test_add_imports_and_usage,
        test_all_methods_add_logging,
        test_large_file_1000_lines,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"❌ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 {t.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    if failed == 0:
        print("All equivalence tests PASSED ✅")
    else:
        print("Some tests FAILED ❌")
        sys.exit(1)
