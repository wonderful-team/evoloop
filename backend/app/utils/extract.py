"""
Content Extraction Utilities

Provides common functions for extracting structured content from text,
including code blocks, JSON, YAML, and tagged sections.
"""

import ast
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_code_block(text: str, lang: str | None = None) -> str | None:
    """
    Extract code block from markdown text.

    Args:
        text: The text containing code blocks
        lang: Optional language filter (e.g., 'json', 'yaml', 'python')

    Returns:
        The extracted code content, or None if not found

    Examples:
        >>> extract_code_block("```json\\n{\\"a\\": 1}\\n```", "json")
        '{"a": 1}'
        >>> extract_code_block("```\\nhello\\n```")
        'hello'
    """
    if not text:
        return None

    # Try specific language block first
    if lang:
        marker = f"```{lang}"
        if marker in text:
            try:
                return text.split(marker, 1)[1].rsplit("```", 1)[0].strip()
            except IndexError:
                pass

    # Try any code block
    if "```" in text:
        parts = text.split("```", 2)
        if len(parts) >= 2:
            # Check if first part has language marker
            code_content = parts[1].strip()
            # Remove language marker if present
            lines = code_content.split("\n", 1)
            if len(lines) == 2 and lines[0] and " " not in lines[0]:
                return lines[1].strip()
            return code_content

    return None


def extract_json_block(text: str) -> dict | None:
    """
    Extract and parse JSON from markdown code block or raw text.

    Args:
        text: Text containing JSON (in code block or raw)

    Returns:
        Parsed JSON dict, or None if parsing fails
    """
    json_str = extract_code_block(text, "json") or extract_code_block(text)
    if not json_str:
        json_str = text.strip()

    return safe_parse_json(json_str)


def extract_yaml_block(text: str) -> str | None:
    """
    Extract YAML content from markdown code block.

    Args:
        text: Text containing YAML code block

    Returns:
        The extracted YAML content, or None if not found
    """
    return extract_code_block(text, "yaml") or extract_code_block(text, "yml")


def extract_section(text: str, markers: list[str]) -> str:
    """
    Extract a section from text based on multiple possible markers.

    Args:
        text: The full text
        markers: List of possible section markers (e.g., ["# Section", "## Section"])

    Returns:
        Text from the first found marker to the end, or original text if no marker found
    """
    for marker in markers:
        if marker in text:
            return text[text.find(marker) :].strip()
    return text


def _extract_json_bounds(text: str) -> str | None:
    """Extract the outermost JSON object/array using brace matching.

    String-aware: braces/commas inside quoted strings are skipped, so
    instructions containing literal ``{``/``}`` do not break the match.
    Handles cases where the LLM output has extra text or truncation.
    """
    text = text.strip()
    start = -1
    for i, c in enumerate(text):
        if c in "{[":
            start = i
            break
    if start < 0:
        return None

    stack = []
    in_string = False
    escaped = False
    end = -1
    for i in range(start, len(text)):
        c = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c in "{[":
            stack.append(c)
        elif c == "}":
            if stack and stack[-1] == "{":
                stack.pop()
                if not stack:
                    end = i + 1
                    break
            else:
                return None  # mismatched
        elif c == "]":
            if stack and stack[-1] == "[":
                stack.pop()
                if not stack:
                    end = i + 1
                    break
            else:
                return None  # mismatched

    if end < 0:
        return None

    return text[start:end]


def _repair_json(text: str) -> str | None:
    """Attempt to repair common JSON issues in LLM output using regex.

    Fixes applied:
      1. Strip control characters (except \\n, \\r, \\t)
      2. Remove trailing commas before ] or }
      3. Replace single-quoted field names with double-quoted
      4. Replace single-quoted string values with double-quoted
      5. Replace unquoted field names (no quotes, only word chars before colon)
    """
    import regex

    if not text:
        return None

    # 1. Strip control characters
    text = regex.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

    # 2. Trailing commas
    text = regex.sub(r",\s*([}\]])", r"\1", text)

    # 3. Single-quoted field names → "key":
    text = regex.sub(r"'([^']+)'(?=\s*:)", r'"\1"', text)

    # 4. Single-quoted string values after colon → "value"
    #    (only where the surrounding structure is likely valid)
    text = regex.sub(r"(:\s*)'([^']*?)'(\s*[,}\]])", r'\1"\2"\3', text)

    # 5. Unquoted field names (word chars before colon, not inside a string)
    text = regex.sub(r"(?<=[\{,]\s*)([A-Za-z_]\w*)\s*:", r'"\1":', text)

    # 6. Unterminated string at the end (truncated output): if the text ends
    #    inside an open double-quoted string, close it with a trailing quote.
    if _ends_inside_string(text):
        text = text + '"'

    # 7. Close any unclosed brackets at the end (truncated output).
    text = _close_unclosed_brackets(text)

    return text


def _close_unclosed_brackets(text: str) -> str:
    """Append closing brackets for any unclosed ``{[`` at the end of ``text``.

    Only used on truncated LLM output that has already been given a closing
    string quote — appends ``}``/``]`` until the bracket stack is empty.
    """
    stack = []
    in_string = False
    escaped = False
    for c in text:
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c in "{[":
            stack.append(c)
        elif c == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif c == "]" and stack and stack[-1] == "[":
            stack.pop()
    if not stack:
        return text
    return text + "".join("}" if b == "{" else "]" for b in reversed(stack))


def _ends_inside_string(text: str) -> bool:
    """True if ``text`` ends while inside an open double-quoted string.

    Walks the text tracking string state (JSON-style escapes) and reports
    whether the last character is inside a string that is not yet closed.
    """
    in_string = False
    escaped = False
    for c in text:
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
    return in_string


def safe_parse_json_value(text: str) -> Any | None:
    """
    Safely parse JSON with multiple fallback strategies, returning any JSON value.

    Order:
      1. Fast path: json.loads
      2. Brace-matched extraction + json.loads
      3. JSON repair (regex) + retry
      4. Python literal eval (for single-quoted dicts)

    Args:
        text: JSON string or Python dict literal

    Returns:
        Parsed value (dict/list/str/int/...), or None if all methods fail
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()
    if not text:
        return None

    # Strategy 1: Fast path
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Brace-matched extraction (handles surrounding noise, truncation)
    bounded = _extract_json_bounds(text)
    if bounded and bounded != text:
        try:
            return json.loads(bounded)
        except json.JSONDecodeError:
            pass

    # Strategy 3: Repair and retry
    candidate = bounded or text
    repaired = _repair_json(candidate)
    if repaired and repaired != candidate:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    # Strategy 4: Python literal eval (for single-quoted dicts)
    if (text.startswith("{") or text.startswith("[")) and "'" in text:
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError) as e:
            # 预期降级路径：literal_eval 失败会继续走后续 repair 策略，
            # 非错误，不应打印 Traceback。
            logger.debug(f"Failed to parse as Python literal: {e}")

    return None


def safe_parse_json(text: str) -> dict | None:
    """
    Safely parse JSON into a dict with multiple fallback strategies.

    Unlike :func:`safe_parse_json_value`, this is strict: only dict results
    are returned, so the return type is guaranteed to be ``dict | None``.

    Args:
        text: JSON object string or Python dict literal

    Returns:
        Parsed dict, or None if all methods fail or the result is not a dict
    """
    value = safe_parse_json_value(text)
    return value if isinstance(value, dict) else None


