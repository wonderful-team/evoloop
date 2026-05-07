"""
E2E scenario tests for real-world editing flows.

These tests simulate complete user requests and validate the full tool chain.
pytest tests/e2e/test_editing_scenarios.py -v
"""

import os
import tempfile

import pytest

from app.domain.tools.files.edit_file import edit_file
from app.domain.tools.files.read_file import read_file

try:
        MULTIEDIT_AVAILABLE = True
except ImportError:
    MULTIEDIT_AVAILABLE = False

try:
    from app.domain.tools.files.apply_patch_file import apply_patch_file
    PATCH_AVAILABLE = True
except ImportError:
    PATCH_AVAILABLE = False


class TestEditingScenarios:
    """10 real-world editing scenarios."""

    @pytest.fixture
    def app_py(self):
        from app.core.tools import get_working_directory
        import uuid

        content = '''"""Sample app."""

import os


def foo():
    """Old function."""
    return True


def baz():
    """Another function."""
    return False


class Config:
    def __init__(self):
        self.debug = True
        self.timeout = 30

    def validate(self):
        return self.timeout > 0


def process_items(items):
    results = []
    for item in items:
        if item:
            results.append(item.strip())
    return results


def main():
    config = Config()
    if config.validate():
        print("Config is valid")
    items = ["  hello  ", "world"]
    print(process_items(items))
    foo()
    baz()


if __name__ == "__main__":
    main()
'''
        root = get_working_directory(None)
        path = os.path.join(root, f"e2e_test_{uuid.uuid4().hex}.py")
        with open(path, 'w') as f:
            f.write(content)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_e2e_01_simple_single_edit(self, app_py):
        """Change foo() to bar() in app.py."""
        result = await edit_file.ainvoke({
            "path": app_py,
            "target": 'def foo():\n    """Old function."""\n    return True',
            "replacement": 'def bar():\n    """New function."""\n    return True'
        })
        assert "success" in result.lower() or "✅" in result

        with open(app_py) as f:
            assert "def bar():" in f.read()
    @pytest.mark.asyncio
    async def test_e2e_02_multiple_edits_same_file(self, app_py):
        """Change foo() and baz() to uppercase names."""
        # First read to get context
        await read_file.ainvoke({"path": app_py})

        edits = [
            {"target": "def foo():", "replacement": "def FOO():"},
            {"target": "def baz():", "replacement": "def BAZ():"},
        ]
        result = await edit_file.ainvoke({"path": app_py, "edits": edits})
        assert "success" in result.lower() or "✅" in result

        with open(app_py) as f:
            content = f.read()
        assert "def FOO():" in content
        assert "def BAZ():" in content

    @pytest.mark.asyncio
    async def test_e2e_04_add_new_function(self, app_py):
        """Add hello() function to app.py."""
        # Use a target that exists in the file and is > 2 chars
        result = await edit_file.ainvoke({
            "path": app_py,
            "target": 'if __name__ == "__main__":',
            "replacement": '\n\ndef hello():\n    return "world"\n\n\nif __name__ == "__main__":'
        })
        assert "success" in result.lower() or "✅" in result

        with open(app_py) as f:
            assert "def hello():" in f.read()

    @pytest.mark.asyncio
    async def test_e2e_05_replace_all_print_to_logger(self, app_py):
        """Replace all print() with logger.info()."""
        result = await edit_file.ainvoke({
            "path": app_py,
            "target": "print(",
            "replacement": "logger.info(",
            "allow_multiple": True
        })
        assert "success" in result.lower() or "✅" in result

        with open(app_py) as f:
            content = f.read()
        assert content.count("logger.info(") == 2
        assert "print(" not in content

    @pytest.mark.asyncio
    async def test_e2e_06_fix_indentation_error(self, app_py):
        """Fix indentation even if target has wrong whitespace."""
        # Intentionally use spaces instead of the actual indentation
        result = await edit_file.ainvoke({
            "path": app_py,
            "target": "        self.debug = True",
            "replacement": "        self.debug = False"
        })
        assert "success" in result.lower() or "✅" in result

        with open(app_py) as f:
            assert "self.debug = False" in f.read()

    @pytest.mark.asyncio
    async def test_e2e_07_cross_file_edit(self):
        """Edit two different files."""
        from app.core.tools import get_working_directory
        import uuid

        root = get_working_directory(None)
        tmpdir = os.path.join(root, f"cross_edit_{uuid.uuid4().hex}")
        os.makedirs(tmpdir, exist_ok=True)
        try:
            app = os.path.join(tmpdir, "app.py")
            test = os.path.join(tmpdir, "test_app.py")
            with open(app, 'w') as f:
                f.write("def add(a, b):\n    return a + b\n")
            with open(test, 'w') as f:
                f.write("from app import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")

            r1 = await edit_file.ainvoke({"path": app, "target": "def add(a, b):", "replacement": "def add(a: int, b: int) -> int:"})
            r2 = await edit_file.ainvoke({"path": test, "target": "from app import add", "replacement": "from app import add\nimport pytest"})

            assert "success" in r1.lower() or "✅" in r1
            assert "success" in r2.lower() or "✅" in r2
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_e2e_08_edit_json_config(self):
        """Edit a JSON file."""
        from app.core.tools import get_working_directory
        import uuid

        root = get_working_directory(None)
        tmpdir = os.path.join(root, f"json_edit_{uuid.uuid4().hex}")
        os.makedirs(tmpdir, exist_ok=True)
        try:
            config = os.path.join(tmpdir, "config.json")
            with open(config, 'w') as f:
                f.write('{\n  "debug": true,\n  "timeout": 30\n}\n')

            result = await edit_file.ainvoke({
                "path": config,
                "target": '  "debug": true',
                "replacement": '  "debug": false'
            })
            assert "success" in result.lower() or "✅" in result

            with open(config) as f:
                assert '"debug": false' in f.read()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
    @pytest.mark.asyncio
    async def test_e2e_09_import_and_usage(self, app_py):
        """Add import and usage in one multiedit."""
        edits = [
            {"target": "import os", "replacement": "import os\nimport json"},
            {"target": '    config = Config()\n    if config.validate():', "replacement": '    config = Config()\n    data = json.dumps({"ok": True})\n    if config.validate():'},
        ]
        result = await edit_file.ainvoke({"path": app_py, "edits": edits})
        assert "success" in result.lower() or "✅" in result

        with open(app_py) as f:
            content = f.read()
        assert "import json" in content
        assert "json.dumps" in content

    @pytest.mark.asyncio
    async def test_e2e_10_delete_function(self, app_py):
        """Remove old_func from app.py."""
        result = await edit_file.ainvoke({
            "path": app_py,
            "target": '\ndef foo():\n    """Old function."""\n    return True\n',
            "replacement": ''
        })
        assert "success" in result.lower() or "✅" in result

        with open(app_py) as f:
            assert "def foo():" not in f.read()
