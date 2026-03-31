"""
Tests for app.utils.collections module.
"""

import pytest

from app.utils.collections import (
    deep_merge,
    filter_none_values,
    filter_empty_values,
    chunk_list,
    merge_lists_unique,
    group_by,
    get_nested_value,
    set_nested_value,
    flatten_dict,
    compact_list,
    unique_ordered,
)


class TestDeepMerge:
    """Test cases for deep_merge function."""

    def test_simple_merge(self):
        """Test simple dictionary merge."""
        base = {"a": 1, "b": 2}
        update = {"b": 3, "c": 4}
        result = deep_merge(base, update)
        assert result == {"a": 1, "b": 3, "c": 4}
    
    def test_nested_merge(self):
        """Test nested dictionary merge."""
        base = {"a": {"b": 1, "c": 2}}
        update = {"a": {"c": 3, "d": 4}}
        result = deep_merge(base, update)
        assert result == {"a": {"b": 1, "c": 3, "d": 4}}
    
    def test_list_concatenation(self):
        """Test that lists are concatenated."""
        base = {"items": [1, 2]}
        update = {"items": [3, 4]}
        result = deep_merge(base, update)
        assert result == {"items": [1, 2, 3, 4]}
    
    def test_empty_dicts(self):
        """Test merging empty dictionaries."""
        result = deep_merge({}, {"a": 1})
        assert result == {"a": 1}
        
        result = deep_merge({"a": 1}, {})
        assert result == {"a": 1}


class TestFilterNoneValues:
    """Test cases for filter_none_values function."""

    def test_removes_none(self):
        """Test None values are removed."""
        data = {"a": 1, "b": None, "c": "value"}
        result = filter_none_values(data)
        assert result == {"a": 1, "c": "value"}
    
    def test_preserves_false_values(self):
        """Test False and 0 are preserved."""
        data = {"a": 0, "b": False, "c": None}
        result = filter_none_values(data)
        assert result == {"a": 0, "b": False}
    
    def test_empty_dict(self):
        """Test empty dictionary."""
        result = filter_none_values({})
        assert result == {}


class TestFilterEmptyValues:
    """Test cases for filter_empty_values function."""

    def test_removes_empty_strings(self):
        """Test empty strings are removed."""
        data = {"a": "value", "b": "", "c": None}
        result = filter_empty_values(data)
        assert result == {"a": "value"}
    
    def test_removes_empty_lists(self):
        """Test empty lists are removed."""
        data = {"a": [1, 2], "b": [], "c": None}
        result = filter_empty_values(data)
        assert result == {"a": [1, 2]}


class TestChunkList:
    """Test cases for chunk_list function."""

    def test_even_chunks(self):
        """Test even chunking."""
        items = [1, 2, 3, 4, 5, 6]
        chunks = list(chunk_list(items, 2))
        assert chunks == [[1, 2], [3, 4], [5, 6]]
    
    def test_uneven_chunks(self):
        """Test uneven chunking."""
        items = [1, 2, 3, 4, 5]
        chunks = list(chunk_list(items, 2))
        assert chunks == [[1, 2], [3, 4], [5]]
    
    def test_chunk_larger_than_list(self):
        """Test chunk size larger than list."""
        items = [1, 2]
        chunks = list(chunk_list(items, 10))
        assert chunks == [[1, 2]]
    
    def test_empty_list(self):
        """Test empty list."""
        chunks = list(chunk_list([], 2))
        assert chunks == []


class TestMergeListsUnique:
    """Test cases for merge_lists_unique function."""

    def test_basic_merge(self):
        """Test basic merge with duplicates."""
        list1 = [1, 2, 3]
        list2 = [3, 4, 5]
        result = merge_lists_unique(list1, list2)
        assert result == [1, 2, 3, 4, 5]
    
    def test_with_key_function(self):
        """Test merge with key function."""
        list1 = [{"id": 1}, {"id": 2}]
        list2 = [{"id": 2}, {"id": 3}]
        result = merge_lists_unique(list1, list2, key=lambda x: x["id"])
        assert len(result) == 3
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        assert result[2]["id"] == 3


class TestGroupBy:
    """Test cases for group_by function."""

    def test_basic_grouping(self):
        """Test basic grouping."""
        items = [
            ("a", 1),
            ("b", 2),
            ("a", 3),
        ]
        result = group_by(items, key_func=lambda x: x[0])
        assert result == {
            "a": [("a", 1), ("a", 3)],
            "b": [("b", 2)],
        }
    
    def test_empty_list(self):
        """Test empty list."""
        result = group_by([], key_func=lambda x: x)
        assert result == {}


class TestGetNestedValue:
    """Test cases for get_nested_value function."""

    def test_simple_path(self):
        """Test simple dot path."""
        data = {"user": {"name": "John"}}
        result = get_nested_value(data, "user.name")
        assert result == "John"
    
    def test_deep_path(self):
        """Test deep nested path."""
        data = {"a": {"b": {"c": "value"}}}
        result = get_nested_value(data, "a.b.c")
        assert result == "value"
    
    def test_missing_path(self):
        """Test missing path returns default."""
        data = {"a": 1}
        result = get_nested_value(data, "a.b.c", default="default")
        assert result == "default"
    
    def test_custom_separator(self):
        """Test custom separator."""
        data = {"a": {"b": "value"}}
        result = get_nested_value(data, "a/b", separator="/")
        assert result == "value"


class TestSetNestedValue:
    """Test cases for set_nested_value function."""

    def test_simple_path(self):
        """Test setting simple nested value."""
        data = {}
        set_nested_value(data, "user.name", "John")
        assert data == {"user": {"name": "John"}}
    
    def test_existing_path(self):
        """Test updating existing nested value."""
        data = {"user": {"name": "Jane", "age": 30}}
        set_nested_value(data, "user.name", "John")
        assert data["user"]["name"] == "John"
        assert data["user"]["age"] == 30


class TestFlattenDict:
    """Test cases for flatten_dict function."""

    def test_basic_flatten(self):
        """Test basic flattening."""
        data = {"a": {"b": 1, "c": {"d": 2}}}
        result = flatten_dict(data)
        assert result == {"a.b": 1, "a.c.d": 2}
    
    def test_already_flat(self):
        """Test already flat dict."""
        data = {"a": 1, "b": 2}
        result = flatten_dict(data)
        assert result == data


class TestCompactList:
    """Test cases for compact_list function."""

    def test_removes_none(self):
        """Test None values are removed."""
        items = [1, None, 2, None, 3]
        result = compact_list(items)
        assert result == [1, 2, 3]
    
    def test_preserves_other_values(self):
        """Test other values are preserved."""
        items = [0, False, "", [], {}]
        result = compact_list(items)
        assert result == [0, False, "", [], {}]


class TestUniqueOrdered:
    """Test cases for unique_ordered function."""

    def test_removes_duplicates(self):
        """Test duplicates are removed while preserving order."""
        items = [1, 2, 1, 3, 2, 4]
        result = unique_ordered(items)
        assert result == [1, 2, 3, 4]
    
    def test_no_duplicates(self):
        """Test list with no duplicates."""
        items = [1, 2, 3]
        result = unique_ordered(items)
        assert result == [1, 2, 3]
    
    def test_empty_list(self):
        """Test empty list."""
        result = unique_ordered([])
        assert result == []
