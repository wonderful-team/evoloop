import asyncio
import os
import shutil

import pytest

from app.domain.tools.coding.lsp import consult_lsp
from app.domain.tools.files.actions.edit import handle_edit

TEST_FILE = "large_test.php"
NUM_CLASSES = 200

def generate_large_php_file():
    lines = []
    lines.append("<?php\n\n")
    lines.append("// This is a large PHP test file\n")

    for i in range(NUM_CLASSES):
        lines.append(f"class Class_{i} {{\n")
        lines.append(f"    public function method_{i}() {{\n")
        lines.append(f"        return {i} * {i};\n")
        lines.append("    }\n")
        lines.append("}\n\n")

    # Inject middle target
    lines.append("class MiddleTargetClass {\n")
    lines.append("    public function sensitiveMethod() {\n")
    lines.append("        echo 'Original Content';\n")
    lines.append("        return true;\n")
    lines.append("    }\n")
    lines.append("}\n\n")

    for i in range(50):
        lines.append(f"class Filler_{i} {{}}\n")

    lines.append("// Call to test LSP\n")
    lines.append("$obj = new MiddleTargetClass();\n")
    lines.append("$obj->sensitiveMethod();\n")

    with open(TEST_FILE, "w") as f:
        f.writelines(lines)

@pytest.mark.asyncio
async def test_php_large_file_editing():
    try:
        print(f"\\nGenerating {TEST_FILE}...")
        generate_large_php_file()
        abs_path = os.path.abspath(TEST_FILE)

        # 1. Fuzzy Edit Test
        print("\\n--- Test 1: Fuzzy Edit PHP (Middle of File) ---")
        # LLM Hallucination: Wrong indentation (2 spaces instead of 4), missing echo single quotes
        target_fuzzy = """class MiddleTargetClass {
  public function sensitiveMethod() {
    echo "Original Content"; 
    return true;
  }
}"""
        # Note: Original uses single quotes 'Original Content' and 4 spaces.
        # Target uses double quotes and 2 spaces.
        # This stresses the fuzzy matcher.

        replacement = """class MiddleTargetClass {
    public function sensitiveMethod() {
        echo 'Patched Content';
        return 'Fixed';
    }
}"""

        res = await handle_edit(TEST_FILE, target=target_fuzzy, content=replacement)
        print(f"Edit Result: {res}")
        assert "Successfully updated" in res

        with open(TEST_FILE) as f: content = f.read()
        assert "Patched Content" in content

        # 2. LSP Test (Optional based on npm)
        if shutil.which("npm") is None:
            print("Skipping LSP test (npm not found)")
            return

        print("\\n--- Test 2: PHP LSP (Definition) ---")
        print("Note: First run might be slow due to 'npm install intelephense'...")

        # Warmup
        await consult_lsp.ainvoke({"action": 'check_errors', "file_path": abs_path})

        # Find definition of sensitiveMethod()
        # Call is at the end.
        with open(TEST_FILE) as f:
            lines = f.readlines()
            call_line = len(lines) # 1-indexed

        print(f"Requesting definition from line {call_line}...")
        # $obj->sensitiveMethod();
        # 0123456
        # Col 7

        # Allow retry for server startup
        for i in range(3):
            def_res = await consult_lsp.ainvoke({
                "action": 'find_definition',
                "file_path": abs_path,
                "line": call_line,
                "character": 7
            })
            if "Error" not in def_res and "No definitions" not in def_res:
                break
            print("Retrying LSP...")
            await asyncio.sleep(2)

        print(f"Definition Result: {def_res}")
        assert TEST_FILE in str(def_res)

    finally:
        if os.path.exists(TEST_FILE):
            os.remove(TEST_FILE)

if __name__ == "__main__":
    asyncio.run(test_php_large_file_editing())
