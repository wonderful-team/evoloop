"""
Collection and Dictionary Utilities

Provides helper functions for working with lists, dictionaries, and other collections.
"""

from typing import Any, Callable, Iterator, TypeVar

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


def deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """
    Deep merge two dictionaries.
    
    Lists are concatenated, nested dicts are merged recursively.
    Values from `update` take precedence.
    
    Args:
        base: Base dictionary
        update: Dictionary to merge into base
    
    Returns:
        New merged dictionary
    
    Examples:
        >>> base = {"a": 1, "b": {"c": 2}}
        >>> update = {"b": {"d": 3}, "e": 4}
        >>> deep_merge(base, update)
        {'a': 1, 'b': {'c': 2, 'd': 3}, 'e': 4}
    """
    result = base.copy()
    
    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        elif key in result and isinstance(result[key], list) and isinstance(value, list):
            result[key] = result[key] + value
        else:
            result[key] = value
    
    return result


def filter_none_values(data: dict[str, Any]) -> dict[str, Any]:
    """
    Remove keys with None values from dictionary.
    
    Args:
        data: Input dictionary
    
    Returns:
        Dictionary without None values
    """
    return {k: v for k, v in data.items() if v is not None}


def filter_empty_values(data: dict[str, Any]) -> dict[str, Any]:
    """
    Remove keys with None or empty values from dictionary.
    
    Args:
        data: Input dictionary
    
    Returns:
        Dictionary without empty values
    """
    return {k: v for k, v in data.items() if v is not None and v != "" and v != []}


def chunk_list(lst: list[T], size: int) -> Iterator[list[T]]:
    """
    Split list into chunks of specified size.
    
    Args:
        lst: List to chunk
        size: Chunk size
    
    Yields:
        Chunks of the list
    
    Examples:
        >>> list(chunk_list([1, 2, 3, 4, 5], 2))
        [[1, 2], [3, 4], [5]]
    """
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def merge_lists_unique(
    *lists: list[T],
    key: Callable[[T], K] | None = None
) -> list[T]:
    """
    Merge multiple lists removing duplicates.
    
    Args:
        *lists: Lists to merge
        key: Optional function to extract comparison key
    
    Returns:
        Merged list with duplicates removed
    """
    seen = set()
    result = []
    
    for lst in lists:
        for item in lst:
            k = key(item) if key else item
            if k not in seen:
                seen.add(k)
                result.append(item)
    
    return result


def group_by(
    lst: list[T],
    key_func: Callable[[T], K]
) -> dict[K, list[T]]:
    """
    Group list items by key function.
    
    Args:
        lst: List to group
        key_func: Function to extract grouping key
    
    Returns:
        Dictionary mapping keys to lists of items
    
    Examples:
        >>> items = [("a", 1), ("b", 2), ("a", 3)]
        >>> group_by(items, lambda x: x[0])
        {'a': [('a', 1), ('a', 3)], 'b': [('b', 2)]}
    """
    result: dict[K, list[T]] = {}
    for item in lst:
        key = key_func(item)
        if key not in result:
            result[key] = []
        result[key].append(item)
    return result


def get_nested_value(
    data: dict[str, Any],
    path: str,
    default: Any = None,
    separator: str = "."
) -> Any:
    """
    Get a value from nested dictionary using dot notation path.
    
    Args:
        data: Nested dictionary
        path: Path like "user.address.city"
        default: Default value if path not found
        separator: Path separator (default ".")
    
    Returns:
        Value at path or default
    """
    keys = path.split(separator)
    current = data
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    
    return current


def set_nested_value(
    data: dict[str, Any],
    path: str,
    value: Any,
    separator: str = "."
) -> None:
    """
    Set a value in nested dictionary using dot notation path.
    
    Args:
        data: Dictionary to modify
        path: Path like "user.address.city"
        value: Value to set
        separator: Path separator
    """
    keys = path.split(separator)
    current = data
    
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    current[keys[-1]] = value


def flatten_dict(
    data: dict[str, Any],
    parent_key: str = "",
    separator: str = "."
) -> dict[str, Any]:
    """
    Flatten nested dictionary to single level with dot notation keys.
    
    Args:
        data: Nested dictionary
        parent_key: Prefix for keys (used in recursion)
        separator: Key separator
    
    Returns:
        Flattened dictionary
    
    Examples:
        >>> flatten_dict({"a": {"b": 1, "c": {"d": 2}}})
        {'a.b': 1, 'a.c.d': 2}
    """
    items: list[tuple[str, Any]] = []
    
    for key, value in data.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key
        
        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, separator).items())
        else:
            items.append((new_key, value))
    
    return dict(items)


def compact_list(lst: list[T | None]) -> list[T]:
    """
    Remove None values from list.
    
    Args:
        lst: List potentially containing None values
    
    Returns:
        List without None values
    """
    return [item for item in lst if item is not None]


def unique_ordered(lst: list[T]) -> list[T]:
    """
    Remove duplicates from list while preserving order.
    
    Args:
        lst: List potentially containing duplicates
    
    Returns:
        List with duplicates removed
    """
    seen = set()
    result = []
    
    for item in lst:
        if item not in seen:
            seen.add(item)
            result.append(item)
    
    return result
