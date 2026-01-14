import os
import re

def scan_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex for JSX text content: >Some Text<
    # Captures text between tags that contains at least one non-whitespace character
    # avoiding simple curly braces which are expressions
    jsx_text_pattern = re.compile(r'>([^<{]+[\u4e00-\u9fa5a-zA-Z]+[^<{]*)<')
    
    # Regex for specific attributes: placeholder="Some Text", title="Some Text", alt="Some Text"
    attr_pattern = re.compile(r'(placeholder|title|label|alt|tooltip)=["\']([^"\']+)["\']')
    
    # Simple regex for Chinese characters anywhere (highest priority for i18n)
    chinese_pattern = re.compile(r'[\u4e00-\u9fa5]+')

    findings = []
    
    # Check for Chinese characters first
    for i, line in enumerate(content.splitlines()):
        if chinese_pattern.search(line) and not line.strip().startswith('//') and not line.strip().startswith('/*'):
             findings.append(f"Line {i+1} (Chinese): {line.strip()}")

    # Check for JSX text (simplified approach: just scan full content and find lines)
    # This acts as a backup for English text detection
    for match in jsx_text_pattern.finditer(content):
        text = match.group(1).strip()
        if text and not text.startswith('{') and len(text) > 1:
             # Find line number
             start_index = match.start()
             line_num = content[:start_index].count('\n') + 1
             # Avoid duplicates if already found by Chinese scanner
             if not any(f"Line {line_num}" in f for f in findings):
                 findings.append(f"Line {line_num} (JSX Text): {text}")

    # Check for Attributes
    for match in attr_pattern.finditer(content):
        attr = match.group(1)
        value = match.group(2)
        if len(value) > 1 and not value.startswith('{'):
             start_index = match.start()
             line_num = content[:start_index].count('\n') + 1
             if not any(f"Line {line_num}" in f for f in findings):
                 findings.append(f"Line {line_num} (Attr {attr}): {value}")

    return findings

def main():
    target_dir = 'evoloop/frontend/src'
    print(f"Scanning {target_dir} for hardcoded strings...\n")
    
    for root, dirs, files in os.walk(target_dir):
        for file in files:
            if file.endswith('.tsx') or file.endswith('.ts'):
                filepath = os.path.join(root, file)
                results = scan_file(filepath)
                if results:
                    print(f"FILE: {filepath}")
                    for r in results:
                        print(f"  {r}")
                    print("")

if __name__ == "__main__":
    main()
