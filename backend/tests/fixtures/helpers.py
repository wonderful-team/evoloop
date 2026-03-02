"""
Test Helper Functions

Shared utilities for test assertions and operations.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar, Union
from unittest.mock import MagicMock

T = TypeVar("T")


def assert_dict_subset(subset: Dict, full_dict: Dict, path: str = "") -> None:
    """
    Assert that full_dict contains all keys and values from subset.

    Args:
        subset: Expected subset of keys/values
        full_dict: Full dictionary to check against
        path: Current path (for nested error messages)

    Raises:
        AssertionError: If subset is not contained in full_dict
    """
    for key, expected_value in subset.items():
        current_path = f"{path}.{key}" if path else key

        assert key in full_dict, f"Key '{current_path}' not found in dictionary"
        actual_value = full_dict[key]

        if isinstance(expected_value, dict):
            assert isinstance(actual_value, dict), \
                f"Value at '{current_path}' should be a dict, got {type(actual_value)}"
            assert_dict_subset(expected_value, actual_value, current_path)
        else:
            assert actual_value == expected_value, \
                f"Value mismatch at '{current_path}': expected {expected_value!r}, got {actual_value!r}"


def assert_contains(haystack: Union[str, list, dict], needle: Any) -> None:
    """
    Assert that haystack contains needle.

    Works with strings, lists, and dictionaries.
    """
    if isinstance(haystack, str):
        assert needle in haystack, f"String does not contain '{needle}': {haystack[:100]}..."
    elif isinstance(haystack, list):
        assert needle in haystack, f"List does not contain {needle!r}: {haystack}"
    elif isinstance(haystack, dict):
        assert needle in haystack, f"Dict does not contain key '{needle}': {list(haystack.keys())}"
    else:
        raise TypeError(f"Cannot check containment for type {type(haystack)}")


async def assert_async_iterator(iterator, expected_count: Optional[int] = None) -> list:
    """
    Consume an async iterator and optionally assert item count.

    Args:
        iterator: Async iterator to consume
        expected_count: If provided, assert this many items

    Returns:
        List of consumed items
    """
    items = []
    async for item in iterator:
        items.append(item)

    if expected_count is not None:
        assert len(items) == expected_count, \
            f"Expected {expected_count} items, got {len(items)}"

    return items


async def wait_for_condition(
    condition: Callable[[], T],
    timeout: float = 5.0,
    interval: float = 0.1,
    message: str = "Condition not met within timeout"
) -> T:
    """
    Wait for a condition to become truthy.

    Args:
        condition: Function to check
        timeout: Maximum time to wait
        interval: Check interval
        message: Error message if timeout

    Returns:
        The truthy result of condition()

    Raises:
        TimeoutError: If condition doesn't become truthy within timeout
    """
    start = asyncio.get_event_loop().time()

    while True:
        result = condition()
        if result:
            return result

        if asyncio.get_event_loop().time() - start > timeout:
            raise TimeoutError(message)

        await asyncio.sleep(interval)


def load_test_data(filename: str, data_dir: Optional[Path] = None) -> Any:
    """
    Load test data from JSON file.

    Args:
        filename: Name of the JSON file
        data_dir: Directory containing test data (defaults to tests/data)

    Returns:
        Parsed JSON data
    """
    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data"

    file_path = data_dir / filename

    if not file_path.exists():
        raise FileNotFoundError(f"Test data file not found: {file_path}")

    with open(file_path, "r") as f:
        return json.load(f)


def create_test_file(path: Path, content: str = "test content") -> Path:
    """
    Create a test file with given content.

    Args:
        path: Path for the file
        content: File content

    Returns:
        Path to created file
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def create_test_project_structure(base_path: Path, structure: Optional[Dict] = None) -> Path:
    """
    Create a test project directory structure.

    Args:
        base_path: Root path for the project
        structure: Dict defining structure (files and dirs)

    Returns:
        Path to project root

    Example:
        structure = {
            "src": {
                "main.py": "print('hello')",
                "utils": {
                    "__init__.py": "",
                    "helpers.py": "def help(): pass"
                }
            },
            "README.md": "# Test Project"
        }
    """
    structure = structure or {
        "src": {
            "main.py": "def main(): pass",
        },
        "README.md": "# Test Project"
    }

    def create_recursive(path: Path, content: Union[str, dict]):
        if isinstance(content, dict):
            path.mkdir(exist_ok=True)
            for name, child_content in content.items():
                create_recursive(path / name, child_content)
        else:
            create_test_file(path, content)

    create_recursive(base_path, structure)
    return base_path


def mock_async_result(return_value: Any) -> MagicMock:
    """
    Create a mock that returns an async result.

    Args:
        return_value: Value to return from the async mock

    Returns:
        Configured MagicMock
    """
    mock = MagicMock()
    mock.__call__ = MagicMock(return_value=async_return(return_value))
    return mock


async def async_return(value: T) -> T:
    """Helper to return a value in an async context."""
    return value


def async_side_effect(values: list) -> Callable:
    """
    Create an async side effect that returns values in sequence.

    Args:
        values: List of values to return on successive calls

    Returns:
        Async function that returns next value on each call
    """
    iterator = iter(values)

    async def _side_effect(*args, **kwargs):
        return next(iterator)

    return _side_effect


def truncate_string(s: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate string for display in test output."""
    if len(s) <= max_length:
        return s
    return s[:max_length - len(suffix)] + suffix


def format_diff(expected: Any, actual: Any) -> str:
    """Format a diff between expected and actual values."""
    import difflib

    expected_str = json.dumps(expected, indent=2, sort_keys=True, default=str)
    actual_str = json.dumps(actual, indent=2, sort_keys=True, default=str)

    diff = difflib.unified_diff(
        expected_str.splitlines(keepends=True),
        actual_str.splitlines(keepends=True),
        fromfile="expected",
        tofile="actual",
        lineterm=""
    )

    return "".join(diff)


class AsyncContextManagerMock:
    """Mock for async context managers."""

    def __init__(self, enter_value: Any = None, exit_value: Any = None):
        self.enter_value = enter_value
        self.exit_value = exit_value
        self.enter_calls = 0
        self.exit_calls = 0

    async def __aenter__(self):
        self.enter_calls += 1
        return self.enter_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.exit_calls += 1
        return self.exit_value


class FakeAsyncIterator:
    """Fake async iterator for testing."""

    def __init__(self, items: list):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item
