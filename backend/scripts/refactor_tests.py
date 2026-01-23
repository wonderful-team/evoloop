
import os
import re

TEST_DIR = "backend/tests/functional/business"

def refactor_file(filepath):
    with open(filepath, "r") as f:
        lines = f.readlines()
    
    new_lines = []
    skip_mode = False
    mock_class_pattern = re.compile(r"^class Mock.*LLM\(RunnableSerializable\):")
    patch_pattern = re.compile(r"^\s+with patch\(.*LLMFactory\.create_llm.*")
    
    for line in lines:
        # 1. Remove Mock Class Definitions
        if mock_class_pattern.match(line):
            skip_mode = True
            continue
        
        if skip_mode:
            # Skip until next top-level class or end of Mock class
            # Assuming Mock classes are at top level or indented
            # A simple heuristic: if line starts with 'class ' or '@', stop skipping
            if (line.startswith("class ") or line.startswith("@")) and not mock_class_pattern.match(line):
                skip_mode = False
            else:
                continue
        
        # 2. Remove 'with patch' and un-indent body
        if patch_pattern.match(line):
            continue
        
        # If previous line was patch (implied by indentation), un-indent
        # But we need to be careful about which lines to unindent.
        # Actually, simpler logic: if line is indented by 12 spaces (inside test method -> inside with patch),
        # dedent to 8 spaces.
        # Standard pytest async def is 4 spaces.
        # with patch is 8 spaces.
        # Body is 12 spaces.
        # So we want to change 12 spaces to 8 spaces IF we are inside a test method.
        
        # Better approach: Just process line by line.
        # If we see `with patch...`, we drop it.
        # Any subsequent lines that have >8 spaces indentation, we reduce indentation by 4.
        # Reset when we hit a line with <= 8 spaces (end of block).
        
        # Wait, this is tricky because `with patch` might be indented differently.
        # Let's use a flag `in_patch_block`? No, because there might be multiple tests.
        
        # Let's try simple regex replacement for un-indentation based on assumed structure.
        # `            # Turn 1` -> `        # Turn 1`
        
        # Check if line corresponds to body of the patch
        # The patch is usually at indentation 8. The body is at 12.
        # We want to keep lines at 4 (def test_...)
        # We want to drop lines at 8 (with patch...)
        # We want to shift lines at 12+ to 8+
        
        # Let's do a 2-pass or smart processing.
        pass

    # New single-pass approach
    processed_lines = []
    inside_mock_class = False
    
    for line in lines:
        # Handle Mock Class removal
        if mock_class_pattern.match(line):
            inside_mock_class = True
            continue
        
        if inside_mock_class:
            if line.startswith("class ") or line.startswith("@pytest") or line.startswith("import"):
                inside_mock_class = False
            else:
                continue

        # Handle patch removal and unindent
        # Removing the `with patch` line
        if "with patch(\"app.core.llm.factory.LLMFactory" in line:
            continue
            
        # Unindenting: match 12 spaces and replace with 8
        # But only if it looks like test body code
        # A safer regex: replace starting 12 spaces with 8 spaces
        if re.match(r"^ {12}", line):
             line = line.replace("    ", "", 1)
        
        processed_lines.append(line)

    with open(filepath, "w") as f:
        f.writelines(processed_lines)
    print(f"Refactored {filepath}")

def main():
    if not os.path.exists(TEST_DIR):
        print(f"Directory not found: {TEST_DIR}")
        return

    for filename in os.listdir(TEST_DIR):
        if filename.startswith("test_") and filename.endswith(".py"):
            refactor_file(os.path.join(TEST_DIR, filename))

if __name__ == "__main__":
    main()
