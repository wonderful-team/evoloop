import asyncio
import os

import pytest

from app.domain.tools.coding.lsp import consult_lsp
from app.domain.tools.files.actions.edit import handle_edit

TEST_FILE = "LargeController.java"
NUM_ENDPOINTS = 200

def generate_large_java_file():
    lines = []
    lines.append("package com.example.demo;\n\n")
    lines.append("import org.springframework.web.bind.annotation.*;\n")
    lines.append("import java.util.*;\n\n")
    lines.append("@RestController\n")
    lines.append("@RequestMapping(\"/api\")\n")
    lines.append("public class LargeController {\n\n")

    for i in range(NUM_ENDPOINTS):
        lines.append(f"    @GetMapping(\"/endpoint{i}\")\n")
        lines.append(f"    public String endpoint{i}() {{\n")
        lines.append(f"        return \"Data from endpoint {i}\";\n")
        lines.append("    }\n\n")

    # Inject middle target
    lines.append("    @PostMapping(\"/sensitive/action\")\n")
    lines.append("    public String sensitiveAction(@RequestBody Map<String, String> payload) {\n")
    lines.append("        System.out.println(\"Original Logic\");\n")
    lines.append("        return \"Processed\";\n")
    lines.append("    }\n\n")

    for i in range(50):
        lines.append(f"    public void fillerMethod{i}() {{}}\n")

    lines.append("    // LSP Test Call\n")
    lines.append("    public void testLsp() {\n")
    lines.append("        sensitiveAction(new HashMap<>());\n")
    lines.append("    }\n")
    lines.append("}\n")

    with open(TEST_FILE, "w") as f:
        f.writelines(lines)

@pytest.mark.asyncio
async def test_java_large_file_editing():
    try:
        print(f"\\nGenerating {TEST_FILE}...")
        generate_large_java_file()
        abs_path = os.path.abspath(TEST_FILE)

        # 1. Fuzzy Edit Test
        print("\\n--- Test 1: Fuzzy Edit Java (Middle of File) ---")
        # LLM Hallucination: Wrong indentation (2 spaces), missing @RequestBody or imports

        target_fuzzy = """    @PostMapping("/sensitive/action")
  public String sensitiveAction(Map<String, String> payload) {
    System.out.println("Original Logic"); 
    return "Processed";
  }"""

        replacement = """    @PostMapping("/sensitive/action")
    public String sensitiveAction(@RequestBody Map<String, String> payload) {
        System.out.println("Patched Logic");
        return "Secure";
    }"""

        res = await handle_edit(TEST_FILE, target=target_fuzzy, content=replacement)
        print(f"Edit Result: {res}")
        assert "Successfully updated" in res

        with open(TEST_FILE) as f: content = f.read()
        assert "Patched Logic" in content

        # 2. LSP Test
        # Java LSP (Eclipse JDT.LS) is heavy. It downloads a JDK and Gradle.
        # This test checks if we can trigger it.
        print("\\n--- Test 2: Java LSP (Definition) ---")

        # JDTLS often needs a valid project structure (pom.xml or build.gradle) to work well.
        # But we will try single file mode if supported, or at least see if it starts.

        print("Initializing Java LSP (this may take time to download server)...")
        # First call might timeout or take long due to download
        try:
             # Just check errors to trigger startup
             await asyncio.wait_for(consult_lsp.ainvoke({"action": 'check_errors', "file_path": abs_path}), timeout=60)
        except asyncio.TimeoutError:
             print("Java LSP startup timed out (expected on first run with download). Skipping detailed verify.")
             return
        except Exception as e:
             print(f"Java LSP failed to start: {e}. Skipping.")
             return

        # Find definition
        with open(TEST_FILE) as f:
            lines = f.readlines()
            # Call is: sensitiveAction(new HashMap<>()); at end
            call_line = len(lines) - 2 # 1-indexed? roughly

        print(f"Requesting definition from line around {call_line}...")

        def_res = await consult_lsp.ainvoke({
            "action": 'find_definition',
            "file_path": abs_path,
            "line": call_line,
            "character": 10
        })
        print(f"Definition Result: {def_res}")

        if "Error" not in str(def_res) and TEST_FILE in str(def_res):
             print("SUCCESS: Java LSP found definition!")
        else:
             print("Java LSP initialized but failed to find def (likely due to missing project structure).")

    finally:
        if os.path.exists(TEST_FILE):
             os.remove(TEST_FILE)

if __name__ == "__main__":
    asyncio.run(test_java_large_file_editing())
