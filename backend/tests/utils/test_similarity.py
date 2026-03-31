"""
Tests for app.utils.similarity module.
"""

import pytest

from app.utils.similarity import (
    find_similar_string,
    find_similar_file,
    calculate_similarity,
    find_all_similar,
    levenshtein_distance,
    normalize_for_comparison,
)


class TestFindSimilarString:
    """Test cases for find_similar_string function."""

    def test_exact_match(self):
        """Test exact string match."""
        candidates = ["apple", "banana", "cherry"]
        result = find_similar_string("apple", candidates, threshold=0.8)
        assert result == "apple"
    
    def test_similar_match(self):
        """Test finding similar string."""
        candidates = ["application", "banana", "cherry"]
        result = find_similar_string("applicatn", candidates, threshold=0.7)
        assert result == "application"
    
    def test_no_match_below_threshold(self):
        """Test when no match meets threshold."""
        candidates = ["apple", "banana", "cherry"]
        result = find_similar_string("xyz", candidates, threshold=0.9)
        assert result is None
    
    def test_empty_candidates(self):
        """Test with empty candidates list."""
        result = find_similar_string("test", [], threshold=0.5)
        assert result is None
    
    def test_partial_match(self):
        """Test partial string matching."""
        candidates = ["src/main.py", "src/utils.py", "tests/test.py"]
        result = find_similar_string("main.py", candidates, threshold=0.6)
        assert result == "src/main.py"


class TestFindSimilarFile:
    """Test cases for find_similar_file function."""

    def test_full_path_match(self):
        """Test matching full file path."""
        repo_files = [
            "/project/src/main.py",
            "/project/src/utils.py",
            "/project/tests/test.py"
        ]
        result = find_similar_file("/project/src/main.py", repo_files)
        assert result == "/project/src/main.py"
    
    def test_filename_only_match(self):
        """Test matching by filename only."""
        repo_files = [
            "/project/src/main.py",
            "/project/src/utils.py",
            "/project/tests/test.py"
        ]
        result = find_similar_file("main.py", repo_files)
        assert result == "/project/src/main.py"
    
    def test_partial_path_match(self):
        """Test matching partial path."""
        repo_files = [
            "/project/src/components/Button.tsx",
            "/project/src/components/Input.tsx",
        ]
        result = find_similar_file("components/Button", repo_files)
        assert result == "/project/src/components/Button.tsx"
    
    def test_no_match(self):
        """Test when no file matches."""
        repo_files = ["/a/b/c.py", "/d/e/f.py"]
        result = find_similar_file("nonexistent.py", repo_files, threshold=0.9)
        assert result is None
    
    def test_empty_repo(self):
        """Test with empty repository."""
        result = find_similar_file("file.py", [])
        assert result is None


class TestCalculateSimilarity:
    """Test cases for calculate_similarity function."""

    def test_identical_strings(self):
        """Test identical strings have similarity 1."""
        score = calculate_similarity("hello", "hello")
        assert score == 1.0 or score >= 0.99
    
    def test_completely_different(self):
        """Test completely different strings."""
        score = calculate_similarity("abc", "xyz")
        # Score should be low but may not be exactly 0
        assert score < 0.5
    
    def test_partial_similarity(self):
        """Test partially similar strings."""
        score = calculate_similarity("hello world", "hello python")
        # Should be higher than completely different
        assert 0.3 < score < 1.0
    
    def test_case_difference(self):
        """Test case insensitive comparison."""
        score = calculate_similarity("Hello", "hello")
        # Should be very similar
        assert score >= 0.8  # Allow for equality
    
    def test_empty_strings(self):
        """Test empty strings."""
        score = calculate_similarity("", "")
        assert score == 1.0
    
    def test_one_empty(self):
        """Test one empty string."""
        score = calculate_similarity("hello", "")
        assert score < 0.5


class TestFindAllSimilar:
    """Test cases for find_all_similar function."""

    def test_basic_search(self):
        """Test basic similar item search."""
        items = [
            {"name": "apple pie", "id": 1},
            {"name": "banana bread", "id": 2},
            {"name": "apple cider", "id": 3},
        ]
        
        results = find_all_similar("apple", items, key_func=lambda x: x["name"], limit=2)
        
        assert len(results) == 2
        # Results should be sorted by similarity
        assert results[0][1] >= results[1][1]
    
    def test_threshold_filtering(self):
        """Test threshold filtering."""
        items = [
            {"name": "apple", "id": 1},
            {"name": "banana", "id": 2},
        ]
        
        results = find_all_similar(
            "apple", 
            items, 
            key_func=lambda x: x["name"], 
            threshold=0.8,
            limit=10
        )
        
        # Only apple should match with high threshold
        assert len(results) == 1
        assert results[0][0]["name"] == "apple"
    
    def test_empty_items(self):
        """Test with empty items list."""
        results = find_all_similar("query", [], key_func=lambda x: x)
        assert results == []
    
    def test_limit_respected(self):
        """Test that limit is respected."""
        items = [{"name": f"item{i}"} for i in range(100)]
        results = find_all_similar("item", items, key_func=lambda x: x["name"], limit=5)
        assert len(results) <= 5


class TestLevenshteinDistance:
    """Test cases for levenshtein_distance function."""

    def test_identical_strings(self):
        """Test identical strings have distance 0."""
        distance = levenshtein_distance("hello", "hello")
        assert distance == 0
    
    def test_one_insertion(self):
        """Test single character insertion."""
        distance = levenshtein_distance("hello", "hellos")
        assert distance == 1
    
    def test_one_deletion(self):
        """Test single character deletion."""
        distance = levenshtein_distance("hello", "hell")
        assert distance == 1
    
    def test_one_substitution(self):
        """Test single character substitution."""
        distance = levenshtein_distance("hello", "hallo")
        assert distance == 1
    
    def test_kitten_to_sitting(self):
        """Test classic example: kitten -> sitting."""
        # k -> s, e -> i, add g
        distance = levenshtein_distance("kitten", "sitting")
        assert distance == 3
    
    def test_empty_string(self):
        """Test with empty string."""
        distance = levenshtein_distance("", "hello")
        assert distance == 5
        
        distance = levenshtein_distance("hello", "")
        assert distance == 5
    
    def test_both_empty(self):
        """Test with both strings empty."""
        distance = levenshtein_distance("", "")
        assert distance == 0


class TestNormalizeForComparison:
    """Test cases for normalize_for_comparison function."""

    def test_lowercase(self):
        """Test conversion to lowercase."""
        result = normalize_for_comparison("Hello World")
        assert result == "hello world"
    
    def test_punctuation_removal(self):
        """Test removal of punctuation."""
        result = normalize_for_comparison("file_name.txt")
        assert "_" not in result
        assert "." not in result
    
    def test_whitespace_normalization(self):
        """Test whitespace normalization."""
        result = normalize_for_comparison("hello    world")
        assert "  " not in result
        assert result == "hello world"
    
    def test_mixed_content(self):
        """Test normalizing mixed content."""
        result = normalize_for_comparison("My-File_Name.TXT")
        assert result == "my file name txt"
    
    def test_empty_string(self):
        """Test with empty string."""
        result = normalize_for_comparison("")
        assert result == ""
