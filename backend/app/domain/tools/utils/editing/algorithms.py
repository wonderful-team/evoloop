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
                matrix[i - 1][j] + 1,      # Deletion
                matrix[i][j - 1] + 1,      # Insertion
                matrix[i - 1][j - 1] + cost # Substitution
            )

    return matrix[len(a)][len(b)]
