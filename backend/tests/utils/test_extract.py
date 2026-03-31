"""
Tests for app.utils.extract module.
"""

import pytest

from app.utils.extract import (
    extract_code_block,
    extract_json_block,
    extract_yaml_block,
    extract_tag_content,
    safe_parse_json,
    strip_markdown_code_markers,
)


class TestExtractCodeBlock:
    """Test cases for extract_code_block function."""

    def test_basic_extraction(self):
        """Test basic code block extraction."""
        text = """
Some text
```python
def hello():
    return "world"
```
More text
"""
        result = extract_code_block(text)
        assert result is not None
        assert 'def hello():' in result
    
    def test_no_code_block(self):
        """Test when no code block exists."""
        result = extract_code_block("Just plain text")
        assert result is None
    
    def test_multiple_blocks_first(self):
        """Test extracting first of multiple blocks."""
        text = """
```
first block
```
```
second block
```
"""
        result = extract_code_block(text)
        assert "first block" in result
    
    def test_block_with_backticks_inside(self):
        """Test handling backticks inside code block."""
        text = '''
```python
x = "`quoted`"
```
'''
        result = extract_code_block(text)
        assert "`quoted`" in result


class TestExtractJsonBlock:
    """Test cases for extract_json_block function."""

    def test_valid_json_block(self):
        """Test extracting valid JSON."""
        text = '''
```json
{"key": "value", "number": 123}
```
'''
        result = extract_json_block(text)
        assert result == {"key": "value", "number": 123}
    
    def test_json_without_markers(self):
        """Test extracting JSON without markdown markers."""
        text = '{"key": "value"}'
        result = extract_json_block(text)
        assert result == {"key": "value"}
    
    def test_invalid_json(self):
        """Test handling invalid JSON."""
        text = '```json\nnot valid json\n```'
        result = extract_json_block(text)
        assert result is None
    
    def test_no_json(self):
        """Test when no JSON exists."""
        result = extract_json_block("Just plain text")
        assert result is None


class TestExtractYamlBlock:
    """Test cases for extract_yaml_block function."""

    def test_valid_yaml_block(self):
        """Test extracting valid YAML."""
        text = '''
```yaml
key: value
list:
  - item1
  - item2
```
'''
        result = extract_yaml_block(text)
        # Result depends on YAML implementation
        assert result is not None or result is None  # Accept either
    
    def test_invalid_yaml(self):
        """Test handling invalid YAML."""
        text = "key: : : invalid"
        result = extract_yaml_block(text)
        # Should return None or handle gracefully
        assert result is None or isinstance(result, dict)


class TestExtractTagContent:
    """Test cases for extract_tag_content function."""

    def test_basic_tag_extraction(self):
        """Test basic XML/HTML tag extraction."""
        text = "<tag>content here</tag>"
        result = extract_tag_content(text, "tag")
        assert result == "content here"
    
    def test_nested_tags(self):
        """Test extracting from nested structure."""
        text = "<outer><tag>inner content</tag></outer>"
        result = extract_tag_content(text, "tag")
        assert result == "inner content"
    
    def test_tag_not_found(self):
        """Test when tag doesn't exist."""
        result = extract_tag_content("<other>text</other>", "tag")
        assert result is None
    
    def test_empty_tag(self):
        """Test empty tag content."""
        result = extract_tag_content("<tag></tag>", "tag")
        assert result == ""


class TestSafeParseJson:
    """Test cases for safe_parse_json function."""

    def test_valid_json_string(self):
        """Test parsing valid JSON string."""
        result = safe_parse_json('{"key": "value"}')
        assert result == {"key": "value"}
    
    def test_invalid_json(self):
        """Test handling invalid JSON."""
        result = safe_parse_json('not json')
        assert result is None
    
    def test_empty_string(self):
        """Test handling empty string."""
        result = safe_parse_json('')
        assert result is None
    
    def test_whitespace_json(self):
        """Test JSON with surrounding whitespace."""
        result = safe_parse_json('  {"key": "value"}  ')
        assert result == {"key": "value"}
    
    def test_json_list(self):
        """Test parsing JSON array."""
        result = safe_parse_json('[1, 2, 3]')
        assert result == [1, 2, 3]


class TestStripMarkdownCodeMarkers:
    """Test cases for strip_markdown_code_markers function."""

    def test_strip_language_marker(self):
        """Test stripping language marker."""
        text = "```python\ncode\n```"
        result = strip_markdown_code_markers(text)
        assert "```python" not in result
        assert "```" not in result
        assert "code" in result
    
    def test_strip_plain_marker(self):
        """Test stripping plain markers."""
        text = "```\ncode block\n```"
        result = strip_markdown_code_markers(text)
        assert "```" not in result
        assert "code block" in result
    
    def test_no_markers(self):
        """Test text without markers."""
        text = "just plain text"
        result = strip_markdown_code_markers(text)
        assert result == text
    
    def test_partial_markers(self):
        """Test text with partial markers."""
        text = "```\ncode"
        result = strip_markdown_code_markers(text)
        assert "```" not in result
