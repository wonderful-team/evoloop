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
        return ipynb_content # Fallback if not valid JSON

    text = ""
    # Handle older nb formats if 'cells' key is missing (unlikely but safe)
    cells = notebook.get('cells', [])

    for cell in cells:
        cell_type = cell.get('cell_type', '')
        source = cell.get('source', [])
        if isinstance(source, str): source = [source]

        if cell_type == 'markdown':
            text += ''.join(source) + '\n\n'
        elif cell_type == 'code':
            text += '```python\n'
            text += ''.join(source) + '\n'
            text += '```\n\n'

            outputs = cell.get('outputs', [])
            if outputs:
                text += '<output>\n'
                for output in outputs:
                    output_type = output.get('output_type', '')
                    if output_type == 'stream':
                        text += ''.join(output.get('text', [])) + '\n'
                    elif output_type == 'execute_result':
                        data = output.get('data', {})
                        text += ''.join(data.get('text/plain', [])) + '\n'
                    elif output_type == 'error':
                        text += ''.join(output.get('traceback', [])) + '\n'
                text += '</output>\n\n'

    return text.strip()


def clean_text(text: str) -> str:
    """
    Clean text content: normalize whitespace, remove excessive newlines.
    """
    if not text:
        return ""

    # Replace multiple empty lines with a single empty line
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

    # Trim lines
    lines = [line.rstrip() for line in text.split('\n')]

    return '\n'.join(lines).strip()


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
