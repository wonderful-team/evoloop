from .strategies import STRATEGIES


def _format_occurrence_hint(content: str, match_text: str, max_snippets: int = 3) -> str:
    """Find all line numbers where match_text appears and return a helpful hint."""
    lines = content.splitlines()
    occurrences = []
    for i, line in enumerate(lines):
        if match_text in line:
            # Show 1 line before and 1 line after for context
            ctx_start = max(0, i - 1)
            ctx_end = min(len(lines), i + 2)
            snippet = "\n".join(f"    {j+1:4d}: {lines[j]}" for j in range(ctx_start, ctx_end))
            occurrences.append(f"  Occurrence at line {i+1}:\n{snippet}")
            if len(occurrences) >= max_snippets:
                remaining = content.count(match_text) - max_snippets
                if remaining > 0:
                    occurrences.append(f"  ... and {remaining} more occurrence(s).")
                break
    return "\n".join(occurrences)


class EditEngine:
    @staticmethod
    def apply_replacement(
        content: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> tuple[bool, str, str]:
        """
        Attempts to replace old_string with new_string in content using multiple fuzzy strategies.

        Returns:
            Tuple[bool, str, str]: (Success, New Content, Log/Error Message)
        """
        if old_string == new_string:
            return False, content, "Error: old_string and new_string are identical."

        # Strategy Loop
        for strategy in STRATEGIES:
            strategy_name = strategy.__name__
            try:
                # Get matches from generator
                matches = list(strategy(content, old_string))

                if not matches:
                    continue

                # Handling multiple matches from a strategy
                if len(matches) > 1 and not replace_all:
                    # Ambiguous match within a single strategy
                    hint = _format_occurrence_hint(content, matches[0])
                    return False, content, (
                        f"Error: Ambiguous match. Strategy '{strategy_name}' found {len(matches)} occurrences.\n"
                        f"Please provide more unique context (include more surrounding lines in 'target').\n"
                        f"Hint:\n{hint}"
                    )

                # If replace_all is False, we already ensured unique match (or errored)
                # If replace_all is True, we might have multiple matches (e.g. from MultiOccurrence)
                # Or we have 1 unique match key, but we want to replace all instances of it in file.

                # Logic:
                # Take the first match (if unique) or iterate?
                # OpenCode Logic: Take the first yielded match that exists in content, and apply replace/replaceAll.

                match_text = matches[0]

                if not replace_all:
                    # Verify uniqueness of the *extracted text* in the whole file to be safe
                    count = content.count(match_text)
                    if count > 1:
                        hint = _format_occurrence_hint(content, match_text)
                        return False, content, (
                            f"Error: The matched block (found by {strategy_name}) appears {count} times in the file.\n"
                            f"Please provide more unique context (include more surrounding lines in 'target').\n"
                            f"Hint:\n{hint}"
                        )

                    new_content = content.replace(match_text, new_string, 1)
                else:
                    # Replace ALL occurrences
                    if len(matches) > 1:
                        # If strategy returned distinct matches (unlikely for most strategies except MultiOccurrence),
                        # we might need to handle them carefully (indices shifting).
                        # But python's string replace is global for the pattern.
                        # If MultiOccurrence returned "foo", "foo", "foo" -> matches=['foo', 'foo', 'foo']
                        # replace('foo') handles all.
                        pass

                    new_content = content.replace(match_text, new_string)

                return True, new_content, f"Applied using strategy: {strategy_name}"

            except Exception:
                # Log and continue to next strategy
                continue

        return False, content, "Error: Could not find target block using any strategy."
