import asyncio
import os

import pytest

from app.domain.tools.coding.lsp import consult_lsp
from app.domain.tools.files.actions.edit import handle_edit

TEST_FILE = "large_fuzzy_test.py"
NUM_LINES = 2000

def generate_large_file():
    lines = []
    lines.append("import os\n")
    lines.append("import sys\n\n")

    for i in range(NUM_LINES):
        lines.append(f"def junk_function_{i}():\n")
        lines.append(f"    # This is filler content line {i}\n")
        lines.append(f"    return {i} * {i}\n\n")

    # Inject specific targets
    # Helper at middle
    lines.append("def middle_target_function():\n")
    lines.append("    print('I am in the middle')\n")
    lines.append("    return True\n\n")

    for i in range(100):
        lines.append(f"def filler_after_{i}(): pass\n")

    lines.append("def end_target_function():\n")
    lines.append("    print('I am at the end')\n")
    lines.append("    return False\n")

    with open(TEST_FILE, "w") as f:
        f.writelines(lines)

@pytest.mark.asyncio
async def test_large_file_manipulation():
    try:
        print(f"\\nGenerating {TEST_FILE} with > {NUM_LINES*3} lines...")
        generate_large_file()

        abs_path = os.path.abspath(TEST_FILE)

        # 1. Fuzzy Edit in Middle of Large File
        print("\\n--- Test 1: Fuzzy Edit (Middle of Large File) ---")
        # Hallucinated indentation or spacing
        target_middle = """def middle_target_function():
  print("I am in the middle") 
  return True"""

        replacement_middle = """def middle_target_function():
    print("Masked: I was edited in the middle")
    return "Edited" """

        res = await handle_edit(TEST_FILE, target=target_middle, content=replacement_middle)
        print(f"Edit Result: {res}")
        assert "Successfully updated" in res

        with open(TEST_FILE) as f: content = f.read()
        assert "Masked: I was edited in the middle" in content

        # 2. LSP Performance on Large File
        print("\\n--- Test 2: LSP Performance (Find Definition in Large File) ---")
        # Find 'junk_function_100' definition.
        # It's generated at the top, so let's try to find it.
        # But wait, we need a CALL to it to find definition?
        # Or we can check errors.
        # Let's add a call at the end
        with open(TEST_FILE, "a") as f:
             f.write("\nres = junk_function_500()\n")

        # Wait for file change event propagation if needed, but we re-open file in LSP

        # Line number: The file is huge.
        # junk_function_500 is roughly at line 500*3 + 2 = 1502.
        # The call is at the very end.

        # Let's check errors first.
        print("Checking errors (warmup)...")
        await consult_lsp.ainvoke({"action": 'check_errors', "file_path": abs_path})

        # Find definition of junk_function_500 from the call at the end
        # We need the line number of the call.
        with open(TEST_FILE) as f:
            lines = f.readlines()
            call_line = len(lines) # 1-indexed

        print(f"Requesting definition from line {call_line}...")
        # Note: junk_function_500 (15 chars)
        # res = junk_function_500()
        # 0123456...
        # Column 10

        def_res = await consult_lsp.ainvoke({
            "action": 'find_definition',
            "file_path": abs_path,
            "line": call_line,
            "character": 10
        })
        print(f"Definition Result: {def_res}")

        # Function 500 is roughly at line 500 * 4 (lines/func) + header ~= 2003.
        # Def returned 2004 in previous run. This is correct.

        # Verify it points to the definition (around line 2000) not the call site (> 6000)
        res_str = str(def_res).strip()
        print(f"LSP Returned: {res_str}")

        # Extract line number
        import re
        match = re.search(r':(\d+)$', res_str)
        if match:
            line_num = int(match.group(1))
            assert 1990 <= line_num <= 2020, f"Definition line {line_num} out of expected range (approx 2004)"
        else:
            # Maybe it returned just the path? No, find_definition returns path:line
             assert TEST_FILE in res_str
             assert "200" in res_str # Loose check

        # Also assert the path matches
        assert str(abs_path) in res_str

        print(f"LSP Validation Passed for file of size {len(lines)} lines.")

    finally:
        if os.path.exists(TEST_FILE):
             os.remove(TEST_FILE)

if __name__ == "__main__":
    asyncio.run(test_large_file_manipulation())
