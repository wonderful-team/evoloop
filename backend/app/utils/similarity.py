"""
String similarity and fuzzy matching utilities.

This module provides tools for finding similar strings, fuzzy searching,
and text similarity calculations.
"""

import logging
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Optional imports
try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    fuzz = None  # type: ignore
    process = None  # type: ignore


def find_similar_string(
    query: str,
    candidates: list[str],
    threshold: float = 0.7,
    scorer: Callable | None = None
) -> str | None:
    """
    Find the most similar string from a list of candidates.
    
    Uses rapidfuzz if available, falls back to simple substring matching.
    
    Args:
        query: The string to search for
        candidates: List of candidate strings
        threshold: Similarity threshold (0.0 to 1.0)
        scorer: Optional custom scorer function (rapidfuzz style)
    
    Returns:
        The best matching string or None if no match above threshold
    
    Example:
        >>> files = ["src/main.py", "src/utils.py", "tests/test.py"]
        >>> find_similar_string("main.py", files, threshold=0.6)
        'src/main.py'
        >>> find_similar_string("nonexistent.py", files, threshold=0.6)
        None
    """
    if not candidates:
        return None
    
    if HAS_RAPIDFUZZ and process:
        # Use rapidfuzz for fuzzy matching
        if scorer is None:
            scorer = fuzz.WRatio
        
        matches = process.extractOne(query, candidates, scorer=scorer)
        if matches and matches[1] >= threshold * 100:
            return matches[0]
    else:
        # Fallback: simple substring matching
        query_lower = query.lower()
        best_match = None
        best_score = 0.0
        
        for candidate in candidates:
            candidate_lower = candidate.lower()
            
            # Exact match
            if query_lower == candidate_lower:
                return candidate
            
            # Substring match
            if query_lower in candidate_lower or candidate_lower in query_lower:
                # Calculate simple similarity based on length ratio
                len_query = len(query)
                len_candidate = len(candidate)
                score = min(len_query, len_candidate) / max(len_query, len_candidate)
                
                if score > best_score:
                    best_score = score
                    best_match = candidate
        
        if best_match and best_score >= threshold:
            return best_match
    
    return None


def find_similar_file(
    file_path: str,
    repo_files: list[str],
    threshold: float = 0.7
) -> str | None:
    """
    Fuzzy search for a file path in a list of repository files.
    
    This function tries multiple matching strategies:
    1. Full path fuzzy match
    2. Filename-only match (if full path fails)
    
    Args:
        file_path: The file path to search for
        repo_files: List of available repository file paths
        threshold: Similarity threshold (0.0 to 1.0)
    
    Returns:
        The best matching file path or None
    
    Example:
        >>> files = ["src/main.py", "src/utils.py", "tests/test.py"]
        >>> find_similar_file("main.py", files)
        'src/main.py'
        >>> find_similar_file("src/utils", files)
        'src/utils.py'
    """
    if not repo_files:
        return None
    
    # First try: full path match
    result = find_similar_string(file_path, repo_files, threshold)
    if result:
        return result
    
    # Second try: match by filename only
    import os
    filename = os.path.basename(file_path)
    
    if filename != file_path:
        all_filenames = [os.path.basename(f) for f in repo_files]
        filename_to_path = {os.path.basename(f): f for f in repo_files}
        
        result = find_similar_string(filename, all_filenames, threshold)
        if result:
            return filename_to_path.get(result)
    
    return None


def calculate_similarity(text1: str, text2: str, method: str = "ratio") -> float:
    """
    Calculate similarity ratio between two strings.
    
    Args:
        text1: First text
        text2: Second text
        method: Similarity method ("ratio", "partial", "token_sort", "token_set")
    
    Returns:
        Similarity ratio between 0.0 and 1.0
    
    Example:
        >>> calculate_similarity("hello world", "hello world!")
        0.96
        >>> calculate_similarity("file.txt", "file_name.txt", method="partial")
        0.67
    """
    if not HAS_RAPIDFUZZ or not fuzz:
        # Fallback: simple character-based similarity
        if text1 == text2:
            return 1.0
        
        # Jaccard similarity on character sets
        set1 = set(text1.lower())
        set2 = set(text2.lower())
        
        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union
    
    # Use rapidfuzz
    if method == "ratio":
        score = fuzz.ratio(text1, text2)
    elif method == "partial":
        score = fuzz.partial_ratio(text1, text2)
    elif method == "token_sort":
        score = fuzz.token_sort_ratio(text1, text2)
    elif method == "token_set":
        score = fuzz.token_set_ratio(text1, text2)
    else:
        score = fuzz.ratio(text1, text2)
    
    return score / 100.0


def find_all_similar(
    query: str,
    candidates: list[T],
    key_func: Callable[[T], str],
    threshold: float = 0.6,
    limit: int = 5
) -> list[tuple[T, float]]:
    """
    Find all similar items from candidates, sorted by similarity.
    
    Args:
        query: The string to search for
        candidates: List of candidate items
        key_func: Function to extract string key from each candidate
        threshold: Minimum similarity threshold
        limit: Maximum number of results
    
    Returns:
        List of (item, similarity_score) tuples, sorted by score descending
    
    Example:
        >>> items = [
        ...     {"name": "hello world", "id": 1},
        ...     {"name": "hello python", "id": 2},
        ...     {"name": "goodbye", "id": 3}
        ... ]
        >>> find_all_similar("hello", items, key_func=lambda x: x["name"])
        [({'name': 'hello world', 'id': 1}, 0.84), ({'name': 'hello python', 'id': 2}, 0.73)]
    """
    if not candidates:
        return []
    
    results = []
    
    for candidate in candidates:
        key = key_func(candidate)
        similarity = calculate_similarity(query, key)
        
        if similarity >= threshold:
            results.append((candidate, similarity))
    
    # Sort by similarity descending
    results.sort(key=lambda x: x[1], reverse=True)
    
    return results[:limit]


def levenshtein_distance(text1: str, text2: str) -> int:
    """
    Calculate Levenshtein edit distance between two strings.
    
    This is the minimum number of single-character edits (insertions,
    deletions, or substitutions) required to change one string into the other.
    
    Args:
        text1: First text
        text2: Second text
    
    Returns:
        Edit distance (0 for identical strings)
    
    Example:
        >>> levenshtein_distance("kitten", "sitting")
        3
        >>> levenshtein_distance("hello", "hello")
        0
    """
    if len(text1) < len(text2):
        return levenshtein_distance(text2, text1)
    
    if len(text2) == 0:
        return len(text1)
    
    previous_row = list(range(len(text2) + 1))
    
    for i, c1 in enumerate(text1):
        current_row = [i + 1]
        
        for j, c2 in enumerate(text2):
            # Cost is 0 if characters match, 1 otherwise
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        
        previous_row = current_row
    
    return previous_row[-1]


def normalize_for_comparison(text: str) -> str:
    """
    Normalize text for better similarity comparison.
    
    - Converts to lowercase
    - Removes extra whitespace
    - Removes common punctuation
    
    Args:
        text: Original text
    
    Returns:
        Normalized text
    """
    import re
    
    # Lowercase
    text = text.lower()
    
    # Remove common punctuation
    text = re.sub(r'[._\-\\/]', ' ', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text
