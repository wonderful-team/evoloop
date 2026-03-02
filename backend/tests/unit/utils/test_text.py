"""
Unit tests for text utilities.
"""

import json
import pytest

from app.utils.text import (
    convert_ipynb_to_text,
    clean_text,
    extract_code_blocks,
)


class TestConvertIpynbToText:
    """Tests for convert_ipynb_to_text function."""

    def test_convert_empty_notebook(self):
        """Test converting empty notebook."""
        notebook = json.dumps({"cells": []})
        result = convert_ipynb_to_text(notebook)
        assert result == ""

    def test_convert_markdown_cell(self):
        """Test converting markdown cell."""
        notebook = json.dumps({
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": ["# Heading\n", "Some text"]
                }
            ]
        })
        result = convert_ipynb_to_text(notebook)
        assert "# Heading" in result
        assert "Some text" in result

    def test_convert_code_cell(self):
        """Test converting code cell."""
        notebook = json.dumps({
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["print('hello')"],
                    "outputs": []
                }
            ]
        })
        result = convert_ipynb_to_text(notebook)
        assert "```python" in result
        assert "print('hello')" in result
        assert "```" in result

    def test_convert_code_cell_with_output(self):
        """Test converting code cell with output."""
        notebook = json.dumps({
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["print('hello')"],
                    "outputs": [
                        {
                            "output_type": "stream",
                            "text": ["hello\n"]
                        }
                    ]
                }
            ]
        })
        result = convert_ipynb_to_text(notebook)
        assert "```python" in result
        assert "<output>" in result
        assert "hello" in result
        assert "</output>" in result

    def test_convert_code_cell_with_execute_result(self):
        """Test converting code cell with execute result."""
        notebook = json.dumps({
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["1 + 1"],
                    "outputs": [
                        {
                            "output_type": "execute_result",
                            "data": {
                                "text/plain": ["2"]
                            }
                        }
                    ]
                }
            ]
        })
        result = convert_ipynb_to_text(notebook)
        assert "2" in result

    def test_convert_code_cell_with_error(self):
        """Test converting code cell with error output."""
        notebook = json.dumps({
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["1/0"],
                    "outputs": [
                        {
                            "output_type": "error",
                            "traceback": ["ZeroDivisionError: division by zero"]
                        }
                    ]
                }
            ]
        })
        result = convert_ipynb_to_text(notebook)
        assert "ZeroDivisionError" in result

    def test_convert_invalid_json(self):
        """Test converting invalid JSON."""
        invalid_content = "not valid json"
        result = convert_ipynb_to_text(invalid_content)
        assert result == invalid_content  # Should return original content

    def test_convert_single_string_source(self):
        """Test converting cell with single string source (not list)."""
        notebook = json.dumps({
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": "Single string"
                }
            ]
        })
        result = convert_ipynb_to_text(notebook)
        assert "Single string" in result


class TestCleanText:
    """Tests for clean_text function."""

    def test_clean_empty_text(self):
        """Test cleaning empty text."""
        result = clean_text("")
        assert result == ""

    def test_clean_none_text(self):
        """Test cleaning None."""
        result = clean_text(None)
        assert result == ""

    def test_clean_whitespace(self):
        """Test cleaning text with excessive whitespace."""
        text = "line1\n\n\n\n\nline2"
        result = clean_text(text)
        assert "\n\n\n" not in result
        assert "line1" in result
        assert "line2" in result

    def test_clean_trailing_whitespace(self):
        """Test cleaning trailing whitespace."""
        text = "line1   \nline2   "
        result = clean_text(text)
        assert "line1   " not in result
        assert "line1" in result

    def test_clean_leading_trailing_newlines(self):
        """Test cleaning leading/trailing newlines."""
        text = "\n\n\ncontent\n\n\n"
        result = clean_text(text)
        assert result == "content"


class TestExtractCodeBlocks:
    """Tests for extract_code_blocks function."""

    def test_extract_single_code_block(self):
        """Test extracting single code block."""
        text = "Some text\n```python\nprint('hello')\n```\nMore text"
        result = extract_code_blocks(text)

        assert len(result) == 1
        assert result[0] == ("python", "print('hello')")

    def test_extract_multiple_code_blocks(self):
        """Test extracting multiple code blocks."""
        text = """
```python
print('hello')
```
Some text
```javascript
console.log('world');
```
"""
        result = extract_code_blocks(text)

        assert len(result) == 2
        assert result[0] == ("python", "print('hello')")
        assert result[1] == ("javascript", "console.log('world');")

    def test_extract_code_block_no_language(self):
        """Test extracting code block without language."""
        text = "```\nsome code\n```"
        result = extract_code_blocks(text)

        assert len(result) == 1
        assert result[0] == ("text", "some code")

    def test_extract_no_code_blocks(self):
        """Test extracting from text with no code blocks."""
        text = "Just plain text without code"
        result = extract_code_blocks(text)

        assert len(result) == 0

    def test_extract_multiline_code_block(self):
        """Test extracting multiline code block."""
        text = """```python
def hello():
    print('world')
    return 42
```"""
        result = extract_code_blocks(text)

        assert len(result) == 1
        assert result[0][0] == "python"
        assert "def hello():" in result[0][1]
        assert "return 42" in result[0][1]
