import json
import re


def convert_ipynb_to_text(ipynb_content: str) -> str:
    """
    Convert Jupyter Notebook content to Markdown text.
    Handles code blocks and output streams.
    """
    try:
        notebook = json.loads(ipynb_content)
    except json.JSONDecodeError:
        return ipynb_content  # Fallback if not valid JSON

    text = ""
    # Handle older nb formats if 'cells' key is missing (unlikely but safe)
    cells = notebook.get("cells", [])

    for cell in cells:
        cell_type = cell.get("cell_type", "")
        source = cell.get("source", [])
        if isinstance(source, str):
            source = [source]

        if cell_type == "markdown":
            text += "".join(source) + "\n\n"
        elif cell_type == "code":
            text += "```python\n"
            text += "".join(source) + "\n"
            text += "```\n\n"

            outputs = cell.get("outputs", [])
            if outputs:
                text += "<output>\n"
                for output in outputs:
                    output_type = output.get("output_type", "")
                    if output_type == "stream":
                        text += "".join(output.get("text", [])) + "\n"
                    elif output_type == "execute_result":
                        data = output.get("data", {})
                        text += "".join(data.get("text/plain", [])) + "\n"
                    elif output_type == "error":
                        text += "".join(output.get("traceback", [])) + "\n"
                text += "</output>\n\n"

    return text.strip()


def clean_text(text: str) -> str:
    """
    Clean text content: normalize whitespace, remove excessive newlines.
    """
    if not text:
        return ""

    # Replace multiple empty lines with a single empty line
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    # Trim lines
    lines = [line.rstrip() for line in text.split("\n")]

    return "\n".join(lines).strip()


def extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """
    Extract code blocks from markdown text.
    Returns list of (language, content).
    """
    # Pattern to match ```lang ... ```
    pattern = r"```(?P<lang>\w+)?\n(?P<code>.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)

    results = []
    for lang, code in matches:
        results.append((lang.strip() if lang else "text", code.strip()))

    return results


def html_to_markdown(html: str, base_url: str = "") -> str:
    """
    Convert HTML content to Markdown format.

    A lightweight implementation that handles common HTML elements:
    - Headers (h1-h6)
    - Paragraphs, line breaks
    - Links and images
    - Lists (ordered/unordered)
    - Code blocks and inline code
    - Tables
    - Emphasis (bold, italic, strikethrough)
    - Blockquotes
    - Horizontal rules

    Args:
        html: HTML content to convert
        base_url: Base URL for resolving relative links

    Returns:
        Markdown formatted text

    Example:
        >>> html = "<h1>Title</h1><p>Hello <b>world</b></p>"
        >>> html_to_markdown(html)
        '# Title\n\nHello **world**'
    """
    if not html:
        return ""

    from bs4 import BeautifulSoup, NavigableString

    def process_element(element) -> str:
        """Process a single HTML element."""
        if isinstance(element, NavigableString):
            text = str(element)
            # Escape Markdown special characters in text
            return _escape_markdown_chars(text)

        if not element.name:
            return ""

        # Skip script and style elements
        if element.name in ["script", "style", "noscript"]:
            return ""

        # Handle different element types
        handlers = {
            "h1": lambda e: f"\n# {_get_text_content(e)}\n",
            "h2": lambda e: f"\n## {_get_text_content(e)}\n",
            "h3": lambda e: f"\n### {_get_text_content(e)}\n",
            "h4": lambda e: f"\n#### {_get_text_content(e)}\n",
            "h5": lambda e: f"\n##### {_get_text_content(e)}\n",
            "h6": lambda e: f"\n###### {_get_text_content(e)}\n",
            "p": lambda e: f"\n{_process_children(e)}\n",
            "br": lambda e: "\n",
            "hr": lambda e: "\n---\n",
            "a": lambda e: _handle_link(e, base_url),
            "img": lambda e: _handle_image(e),
            "ul": _handle_unordered_list,
            "ol": _handle_ordered_list,
            "li": lambda e: _get_text_content(e).strip(),
            "blockquote": lambda e: _handle_blockquote(e),
            "code": lambda e: f"`{_get_text_content(e)}`",
            "pre": _handle_code_block,
            "strong": lambda e: f"**{_get_text_content(e)}**",
            "b": lambda e: f"**{_get_text_content(e)}**",
            "em": lambda e: f"*{_get_text_content(e)}*",
            "i": lambda e: f"*{_get_text_content(e)}*",
            "del": lambda e: f"~~{_get_text_content(e)}~~",
            "table": _handle_table,
            "div": lambda e: f"\n{_process_children(e)}\n",
            "span": lambda e: _process_children(e),
            "article": lambda e: f"\n{_process_children(e)}\n",
            "section": lambda e: f"\n{_process_children(e)}\n",
        }

        handler = handlers.get(element.name, _process_children)
        return handler(element)

    def _process_children(element) -> str:
        """Process all children of an element."""
        return "".join(process_element(child) for child in element.children)

    def _get_text_content(element) -> str:
        """Get text content of an element."""
        if isinstance(element, NavigableString):
            return str(element)
        return "".join(
            str(child) if isinstance(child, NavigableString) else _get_text_content(child)
            for child in element.children
        )

    def _handle_link(element, base_url: str) -> str:
        """Handle anchor elements."""
        href = element.get("href", "")
        text = _get_text_content(element).strip() or href

        # Resolve relative URLs
        if base_url and href and not href.startswith(("http://", "https://", "#", "mailto:")):
            from urllib.parse import urljoin
            href = urljoin(base_url, href)

        return f"[{text}]({href})"

    def _handle_image(element) -> str:
        """Handle image elements."""
        src = element.get("src", "")
        alt = element.get("alt", "")
        title = element.get("title", "")

        if title:
            return f"![{alt}]({src} \"{title}\")"
        return f"![{alt}]({src})"

    def _handle_unordered_list(element) -> str:
        """Handle unordered lists."""
        items = []
        for li in element.find_all("li", recursive=False):
            items.append(f"- {_get_text_content(li).strip()}")
        return "\n" + "\n".join(items) + "\n"

    def _handle_ordered_list(element) -> str:
        """Handle ordered lists."""
        items = []
        for i, li in enumerate(element.find_all("li", recursive=False), 1):
            items.append(f"{i}. {_get_text_content(li).strip()}")
        return "\n" + "\n".join(items) + "\n"

    def _handle_blockquote(element) -> str:
        """Handle blockquote elements."""
        text = _get_text_content(element).strip()
        lines = text.split("\n")
        quoted = "\n".join(f"> {line}" for line in lines)
        return f"\n{quoted}\n"

    def _handle_code_block(element) -> str:
        """Handle pre/code blocks."""
        code = element.find("code")
        if code:
            # Extract language from class
            classes = code.get("class", [])
            language = ""
            for cls in classes:
                if cls.startswith("language-"):
                    language = cls[9:]
                    break
            content = _get_text_content(code)
        else:
            language = ""
            content = _get_text_content(element)

        return f"\n```{language}\n{content.strip()}\n```\n"

    def _handle_table(element) -> str:
        """Handle table elements."""
        rows = []

        # Extract headers
        thead = element.find("thead")
        if thead:
            header_row = thead.find("tr")
            if header_row:
                headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
                if headers:
                    rows.append("| " + " | ".join(headers) + " |")
                    rows.append("| " + " | ".join(["---"] * len(headers)) + " |")

        # Extract body rows
        tbody = element.find("tbody") or element
        for tr in tbody.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells and not (len(cells) == len(headers) and all(c == h for c, h in zip(cells, headers))):
                rows.append("| " + " | ".join(cells) + " |")

        return "\n" + "\n".join(rows) + "\n" if rows else ""

    def _escape_markdown_chars(text: str) -> str:
        """Escape Markdown special characters in text."""
        # Only escape in specific contexts to avoid over-escaping
        chars_to_escape = ["*", "`", "[", "]", "#", ">", "|"]
        for char in chars_to_escape:
            text = text.replace(char, f"\\{char}")
        return text

    # Parse and convert
    soup = BeautifulSoup(html, "html.parser")

    # Find body or use entire document
    body = soup.find("body") or soup

    result = process_element(body)

    # Clean up extra whitespace
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
