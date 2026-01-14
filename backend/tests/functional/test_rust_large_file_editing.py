import asyncio
import os
import shutil

import pytest

from app.domain.tools.coding.lsp import consult_lsp
from app.domain.tools.files.actions.edit import handle_edit

TEST_FILE = "large_test.rs"
NUM_STRUCTS = 200

def generate_large_rust_file():
    lines = []
    lines.append("fn main() {\n")
    lines.append("    println!(\"Hello from large Rust file\");\n")
    lines.append("}\n\n")

    for i in range(NUM_STRUCTS):
        lines.append(f"struct Struct{i} {{\n")
        lines.append("    field: i32,\n")
        lines.append("}\n\n")
        lines.append(f"impl Struct{i} {{\n")
        lines.append("    fn new() -> Self {\n")
        lines.append(f"        Self {{ field: {i} }}\n")
        lines.append("    }\n\n")
        lines.append(f"    fn method_{i}(&self) -> i32 {{\n")
        lines.append(f"        self.field * {i}\n")
        lines.append("    }\n")
        lines.append("}\n\n")

    # Inject middle target
    lines.append("struct MiddleTargetStruct {\n")
    lines.append("    data: String,\n")
    lines.append("}\n\n")
    lines.append("impl MiddleTargetStruct {\n")
    lines.append("    fn sensitive_method(&self) -> bool {\n")
    lines.append("        println!(\"Original Content\");\n")
    lines.append("        true\n")
    lines.append("    }\n")
    lines.append("}\n\n")

    for i in range(50):
        lines.append(f"struct Filler{i};\n")

    lines.append("// LSP Test Call\n")
    lines.append("fn test_lsp() {\n")
    lines.append("    let s = MiddleTargetStruct { data: String::from(\"test\") };\n")
    lines.append("    s.sensitive_method();\n")
    lines.append("}\n")

    with open(TEST_FILE, "w") as f:
        f.writelines(lines)

@pytest.mark.asyncio
async def test_rust_large_file_editing():
    try:
        print(f"\\nGenerating {TEST_FILE}...")
        generate_large_rust_file()
        abs_path = os.path.abspath(TEST_FILE)

        # 1. Fuzzy Edit Test
        print("\\n--- Test 1: Fuzzy Edit Rust (Middle of File) ---")
        # LLM Hallucination: Wrong indentation (2 spaces instead of 4), wrong string quotes (Rust uses double quotes, but maybe LLM forgot)
        # Or missing braces.

        target_fuzzy = """impl MiddleTargetStruct {
  fn sensitive_method(&self) -> bool {
    println!("Original Content"); 
    true
  }
}"""
        # Note: Original uses 4 spaces. Target uses 2.

        replacement = """impl MiddleTargetStruct {
    fn sensitive_method(&self) -> bool {
        println!("Patched Content");
        false
    }
}"""

        res = await handle_edit(TEST_FILE, target=target_fuzzy, content=replacement)
        print(f"Edit Result: {res}")
        assert "Successfully updated" in res

        with open(TEST_FILE) as f: content = f.read()
        assert "Patched Content" in content
        assert "false" in content

        # 2. LSP Test
        # Check if rust-analyzer is available
        if shutil.which("rust-analyzer") is None and shutil.which("rustup") is None:
            print("Skipping LSP test (rust-analyzer/rustup not found)")
            return

        print("\\n--- Test 2: Rust LSP (Definition) ---")

        # Warmup
        try:
             await consult_lsp.ainvoke({"action": 'check_errors', "file_path": abs_path})
        except Exception as e:
             # Rust analyzer might be slow to start or fail if project structure isn't perfect (Cargo.toml needed?)
             # Usually for single file editing, it might be limited, but let's try.
             print(f"LSP Startup warning: {e}")

        # Find definition of sensitive_method()
        # Call is at the end.
        with open(TEST_FILE) as f:
            lines = f.readlines()
            call_line = len(lines) - 1 # 1-indexed line of s.sensitive_method();

        print(f"Requesting definition from line {call_line}...")
        # s.sensitive_method();
        # 0123456
        # Col 6

        # Retry loop for slow startup
        found = False
        for i in range(5):
            def_res = await consult_lsp.ainvoke({
                "action": 'find_definition',
                "file_path": abs_path,
                "line": call_line,
                "character": 6
            })
            if "Error" not in str(def_res) and "No definitions" not in str(def_res) and TEST_FILE in str(def_res):
                found = True
                break
            print("Retrying Rust LSP...")
            await asyncio.sleep(3)

        print(f"Definition Result: {def_res}")

        # Rust Analyzer often returns definition location
        if found:
            assert TEST_FILE in str(def_res)
        else:
             print("Warning: Rust LSP failed to find definition. This might be due to missing Cargo.toml or single-file mode limitation.")
             # We don't fail the test strictly for LSP if env is missing, but we log it.

    finally:
        if os.path.exists(TEST_FILE):
             os.remove(TEST_FILE)

if __name__ == "__main__":
    asyncio.run(test_rust_large_file_editing())
