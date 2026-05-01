"""
Content Extraction Utilities

Provides common functions for extracting structured content from text,
including code blocks, JSON, YAML, and tagged sections.
"""

import ast
import json
import logging

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
                return text.split(marker, 1)[1].split("```", 1)[0].strip()
            except IndexError:
                pass
    
    # Try any code block
    if "```" in text:
        parts = text.split("```", 2)
        if len(parts) >= 2:
            # Check if first part has language marker
            code_content = parts[1].strip()
            # Remove language marker if present
            lines = code_content.split('\n', 1)
            if len(lines) == 2 and lines[0] and ' ' not in lines[0]:
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


def extract_tag_content(text: str, tag: str) -> str | None:
    """
    Extract content from XML/HTML-like tags.
    
    Args:
        text: The text containing tagged content
        tag: The tag name (e.g., 'report', 'think', 'outcome')
    
    Returns:
        The extracted content, or None if tag not found
    
    Examples:
        >>> extract_tag_content("<evoloop_final_report>hello</evoloop_final_report>", "evoloop_final_report")
        'hello'
        >>> extract_tag_content("<audit>\\n  review\\n</audit>", "audit")
        'review'
    """
    import re
    pattern = rf"<{tag}>(.*?)</{tag}>"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


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
            return text[text.find(marker):].strip()
    return text


def safe_parse_json(text: str) -> dict | None:
    """
    Safely parse JSON with fallback to Python literal eval.
    
    Args:
        text: JSON string or Python dict literal
    
    Returns:
        Parsed dict, or None if both methods fail
    """
    if not text or not isinstance(text, str):
        return None
    
    text = text.strip()
    if not text:
        return None
    
    # Try JSON first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try Python literal eval (for single-quoted dicts)
    if (text.startswith("{") or text.startswith("[")) and "'" in text:
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError) as e:
            logger.debug(f"Failed to parse as Python literal: {e}")
    
    return None


def strip_markdown_code_markers(text: str) -> str:
    """
    Remove markdown code block markers from text.
    
    Args:
        text: Text potentially wrapped in ``` markers
    
    Returns:
        Clean text without markers
    """
    text = text.strip()
    
    # Remove leading ```lang
    if text.startswith("```"):
        lines = text.split('\n', 1)
        if len(lines) == 2:
            text = lines[1]
        else:
            text = text[3:]
    
    # Remove trailing ```
    if text.endswith("```"):
        text = text[:-3].strip()
    
    return text


def extract_all_code_blocks(text: str) -> list[tuple[str | None, str]]:
    """
    Extract all code blocks from text.
    
    Args:
        text: Text containing multiple code blocks
    
    Returns:
        List of (language, content) tuples
    """
    import re
    pattern = r"```(?P<lang>\w+)?\n(?P<code>.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    
    results = []
    for lang, code in matches:
        results.append((lang.strip() if lang else None, code.strip()))
    
    return results
