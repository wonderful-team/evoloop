from collections.abc import Generator

from app.utils.text import normalize_ws

from .algorithms import levenshtein

# Similarity thresholds
SINGLE_CANDIDATE_SIMILARITY_THRESHOLD = 0.0
MULTIPLE_CANDIDATES_SIMILARITY_THRESHOLD = 0.3


def simple_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Exact match replacer."""
    if find in content:
        yield find


def line_trimmed_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Matches content ignoring leading/trailing whitespace of each line."""
    original_lines = content.splitlines()
    search_lines = find.splitlines()

    if not search_lines:
        return

    # Normalize: Remove trailing empty line in search if present
    # (Matches TS implementation logic)
    if search_lines[-1].strip() == "":
        search_lines.pop()

    search_len = len(search_lines)
    if search_len == 0:
        return

    for i in range(len(original_lines) - search_len + 1):
        match = True
        for j in range(search_len):
            if original_lines[i + j].strip() != search_lines[j].strip():
                match = False
                break

        if match:
            # Reconstruct the original block from the content
            # We need to preserve the original newlines/formatting
            # Find the start index in the original content

            # This is a simplified reconstruction relying on splitlines behavior
            # Ideally we would track indices, but Python's splitlines drops delimiters by default.
            # Let's perform a substring extraction based on line indices.

            # Calculate char index
            # Re-split with keepends=True to calculate offsets accurately
            lines_with_ends = content.splitlines(keepends=True)

            start_index = sum(len(lines_with_ends[k]) for k in range(i))
            end_index = start_index + sum(len(lines_with_ends[k]) for k in range(i, i + search_len))

            # If the last line of the match didn't have a newline in the original but splitlines added one implicitly?
            # splitlines(keepends=True) keeps the \n.

            yield content[start_index:end_index].rstrip("\n")  # Yield trim optional


def block_anchor_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    Matches a block based on the resemblance of its first and last lines (anchors),
    and fuzzy matching the middle content.
    """
    original_lines = content.splitlines()
    search_lines = find.splitlines()

    if len(search_lines) < 3:
        return

    if search_lines[-1].strip() == "":
        search_lines.pop()

    if len(search_lines) < 2:
        return

    first_line_search = search_lines[0].strip()
    last_line_search = search_lines[-1].strip()
    search_block_size = len(search_lines)

    candidates: list[tuple[int, int]] = []

    # Find candidates where Start and End lines match anchors
    for i in range(len(original_lines)):
        if original_lines[i].strip() != first_line_search:
            continue

        for j in range(i + 2, len(original_lines)):
            if original_lines[j].strip() == last_line_search:
                candidates.append((i, j))
                break  # Only match first occurrences of end line for this start line

    if not candidates:
        return

    best_match: tuple[int, int] | None = None
    max_similarity = -1.0

    lines_with_ends = content.splitlines(keepends=True)

    for start_line, end_line in candidates:
        actual_block_size = end_line - start_line + 1
        similarity = 0.0

        # Determine lines to check in the middle
        lines_to_check = min(search_block_size - 2, actual_block_size - 2)

        if lines_to_check > 0:
            current_similarity_sum = 0.0
            for k in range(1, lines_to_check + 1):
                # We compare the first N middle lines bounded by lines_to_check
                # Note: TS impl iterates `j < searchBlockSize - 1 && j < actualBlockSize - 1`
                # which effectively checks the top part of the middle section.

                original_line = original_lines[start_line + k].strip()
                search_line = search_lines[k].strip()

                max_len = max(len(original_line), len(search_line))
                if max_len == 0:
                    continue

                distance = levenshtein(original_line, search_line)
                current_similarity_sum += 1.0 - distance / max_len

            similarity = current_similarity_sum / lines_to_check
        else:
            similarity = 1.0

        # Heuristic for single candidate
        if len(candidates) == 1:
            if similarity >= SINGLE_CANDIDATE_SIMILARITY_THRESHOLD:
                best_match = (start_line, end_line)
                break
        else:
            if similarity > max_similarity:
                max_similarity = similarity
                best_match = (start_line, end_line)

    if best_match and (len(candidates) == 1 or max_similarity >= MULTIPLE_CANDIDATES_SIMILARITY_THRESHOLD):
        start_line, end_line = best_match

        start_index = sum(len(lines_with_ends[k]) for k in range(start_line))
        end_index = start_index + sum(len(lines_with_ends[k]) for k in range(start_line, end_line + 1))

        yield content[start_index:end_index].rstrip("\n")


def whitespace_normalized_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Matches content treating all whitespace sequences as a single space."""

    normalized_find = normalize_ws(find)

    # Handle block match
    # Heuristic: Sliding window over lines
    # This assumes the match is contiguous text

    # Naive implementation: Normalize WHOLE content and find index?
    # That corrupts indices.
    # Sliding window is better.

    original_lines = content.splitlines()
    find_lines = find.splitlines()

    if not find_lines:
        return

    # Window size in lines
    search_window_size = len(find_lines)

    lines_with_ends = content.splitlines(keepends=True)

    for i in range(len(original_lines) - search_window_size + 1):
        window_block = "".join(lines_with_ends[i : i + search_window_size])
        if normalize_ws(window_block) == normalized_find:
            yield window_block.rstrip("\n")


def trimmed_boundary_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Matches content if the trimmed version matches."""
    trimmed_find = find.strip()
    if trimmed_find == find:
        return

    if trimmed_find in content:
        yield trimmed_find

    # Also check blocks
    original_lines = content.splitlines()
    find_lines = find.splitlines()

    if not find_lines:
        return

    search_len = len(find_lines)
    lines_with_ends = content.splitlines(keepends=True)

    for i in range(len(original_lines) - search_len + 1):
        block_lines = original_lines[i : i + search_len]
        block = "\n".join(block_lines)
        if block.strip() == trimmed_find:
            # Reconstruct exact block from lines_with_ends
            start_index = sum(len(lines_with_ends[k]) for k in range(i))
            end_index = start_index + sum(len(lines_with_ends[k]) for k in range(i, i + search_len))
            yield content[start_index:end_index].rstrip("\n")


def escape_normalized_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Matches content trying to unescape common sequences."""

    def unescape(s: str) -> str:
        # Simple unescape for common chars
        return s.replace(r"\n", "\n").replace(r"\t", "\t").replace(r"\"", '"').replace(r"\'", "'")

    unescaped_find = unescape(find)
    if unescaped_find == find:
        return

    if unescaped_find in content:
        yield unescaped_find


def context_aware_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    Uses surrounding lines as anchors to find a block, then fuzzy matches the middle.
    Similar to BlockAnchor but for larger context chunks.
    Opencode's implementation uses the first and last line of 'find' as anchors.
    """
    find_lines = find.splitlines()
    if len(find_lines) < 3:
        return

    if find_lines[-1].strip() == "":
        find_lines.pop()

    first_line = find_lines[0].strip()
    last_line = find_lines[-1].strip()

    original_lines = content.splitlines()
    lines_with_ends = content.splitlines(keepends=True)

    for i in range(len(original_lines)):
        if original_lines[i].strip() != first_line:
            continue

        for j in range(i + 2, len(original_lines)):
            if original_lines[j].strip() == last_line:
                # Candidate block found
                block_lines = original_lines[i : j + 1]

                # Verify length matches roughly (allow some variance?)
                # Opencode checks if blockLines.length === findLines.length
                if len(block_lines) != len(find_lines):
                    continue

                # Middle match check
                matching_lines = 0
                total_non_empty = 0

                for k in range(1, len(block_lines) - 1):
                    bl = block_lines[k].strip()
                    fl = find_lines[k].strip()

                    if bl or fl:
                        total_non_empty += 1
                        if bl == fl:
                            matching_lines += 1

                if total_non_empty == 0 or (matching_lines / total_non_empty >= 0.5):
                    # Found match
                    start_index = sum(len(lines_with_ends[k]) for k in range(i))
                    end_index = start_index + sum(len(lines_with_ends[k]) for k in range(i, j + 1))
                    yield content[start_index:end_index].rstrip("\n")
                    return  # Only yield first match per logic


def indentation_flexible_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    Matches block regardless of indentation level, effectively shifting
    the search block to match the target's indentation.
    """
    find_lines = find.splitlines()
    if not find_lines:
        return

    def get_indent(line: str) -> int:
        return len(line) - len(line.lstrip())

    # Filter out empty lines for indent calculation
    non_empty_find = [line for line in find_lines if line.strip()]
    if not non_empty_find:
        # If all empty, fallback to simple trim match
        yield from trimmed_boundary_replacer(content, find)
        return

    # Calculate minimum indentation of the search block
    min_find_indent = min(get_indent(line) for line in non_empty_find)

    # Create a normalized version of the search block (0-indent)
    normalized_find_lines = []
    for line in find_lines:
        if line.strip():
            normalized_find_lines.append(line[min_find_indent:])
        else:
            normalized_find_lines.append(line)

    original_lines = content.splitlines()
    lines_with_ends = content.splitlines(keepends=True)
    search_len = len(find_lines)

    for i in range(len(original_lines) - search_len + 1):
        block_lines = original_lines[i : i + search_len]

        # Calculate min indent of this candidate block
        non_empty_block = [line for line in block_lines if line.strip()]
        if not non_empty_block:
            continue

        min_block_indent = min(get_indent(line) for line in non_empty_block)

        # Create normalized candidate
        normalized_block_lines = []
        for line in block_lines:
            if line.strip():
                # Handle case where line is shorter than min indent (shouldn't happen if min is correct)
                if len(line) >= min_block_indent:
                    normalized_block_lines.append(line[min_block_indent:])
                else:
                    normalized_block_lines.append(line)
            else:
                normalized_block_lines.append(line)

        # Check match
        # We need strict match on normalized content
        match = True
        for j in range(search_len):
            if normalized_block_lines[j] != normalized_find_lines[j]:
                match = False
                break

        if match:
            # Found it! Yield the ORIGINAL block from content
            start_index = sum(len(lines_with_ends[k]) for k in range(i))
            end_index = start_index + sum(len(lines_with_ends[k]) for k in range(i, i + search_len))
            yield content[start_index:end_index].rstrip("\n")


def multi_occurrence_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    Yields ALL occurrences of exact match. This is crucial for 'replaceAll' logic.
    Other strategies typically yield and return (finding only first).
    """
    start = 0
    while True:
        idx = content.find(find, start)
        if idx == -1:
            break
        yield find
        start = idx + len(find)


# Strategy List
STRATEGIES = [
    simple_replacer,
    line_trimmed_replacer,
    block_anchor_replacer,
    whitespace_normalized_replacer,
    trimmed_boundary_replacer,
    escape_normalized_replacer,
    context_aware_replacer,
    indentation_flexible_replacer,
    multi_occurrence_replacer,
]
