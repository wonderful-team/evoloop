import difflib

from .models import MatchConfidence


def levenshtein(a: str, b: str) -> int:
    """
    Calculates the Levenshtein distance between two strings using dynamic programming.
    """
    if not a:
        return len(b)
    if not b:
        return len(a)

    # Initialize matrix
    matrix = [[0 for _ in range(len(b) + 1)] for _ in range(len(a) + 1)]

    # Initialize first row and column
    for i in range(len(a) + 1):
        matrix[i][0] = i
    for j in range(len(b) + 1):
        matrix[0][j] = j

    # Fill matrix
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,  # Deletion
                matrix[i][j - 1] + 1,  # Insertion
                matrix[i - 1][j - 1] + cost,  # Substitution
            )

    return matrix[len(a)][len(b)]


def generate_unified_diff(
    original: str, modified: str, file_path: str = "file", context_lines: int = 3
) -> str:
    """Generate unified diff format."""
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    # Ensure lines end with newline for proper diff
    if original_lines and not original_lines[-1].endswith("\n"):
        original_lines[-1] += "\n"
    if modified_lines and not modified_lines[-1].endswith("\n"):
        modified_lines[-1] += "\n"

    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=context_lines,
    )

    return "".join(diff)


def calculate_confidence(
    strategy_name: str | None,
    is_exact_match: bool,
    match_count: int,
    similarity_score: float = 1.0,
) -> MatchConfidence:
    """Calculate confidence level based on matching strategy and results."""
    if is_exact_match and match_count == 1:
        return MatchConfidence.HIGH

    if match_count > 1:
        return MatchConfidence.LOW

    if strategy_name == "simple_replacer":
        return MatchConfidence.HIGH

    if similarity_score >= 0.8:
        return MatchConfidence.HIGH
    elif similarity_score >= 0.5:
        return MatchConfidence.MEDIUM
    else:
        return MatchConfidence.LOW
