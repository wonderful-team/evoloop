import asyncio
import os

import pytest

from app.domain.tools.coding.lsp import consult_lsp


@pytest.mark.asyncio
async def test_complete_lsp_capabilities():
    filename = "temp_lsp_test.py"
    # Content has:
    # 1. Type error (line 2)
    # 2. Function definition (line 4)
    # 3. Usage of function (line 8)
    # 4. Docstring for hover (line 5)
    content = """def bad_function() -> int:
    return "string"

def good_function(x: int) -> int:
    '''Returns the square of x.'''
    return x * x

res = good_function(5)
"""

    with open(filename, "w") as f:
        f.write(content)

    abs_path = os.path.abspath(filename)
    print(f"Testing LSP on {abs_path}")

    try:
        # 1. Check Errors
        print("\n--- Testing Check Errors ---")
        # Retry logic is good for async LSP startup
        diagnostics = ""
        for i in range(20):
            result = await consult_lsp.ainvoke({"action": 'check_errors', "file_path": abs_path})
            if "Error" in result and "Pyright" in result:
                diagnostics = result
                break
            await asyncio.sleep(1)

        print(f"Diagnostics: {diagnostics}")
        # Verify specific type error is caught
        assert "Type \"Literal['string']\" is not assignable to return type \"int\"" in diagnostics

        # 2. Find Definition
        # Call is at line 8: "res = good_function(5)"
        # "good_function" starts around character 7 (0-indexed 6)
        print("\n--- Testing Find Definition ---")
        # Line 8, column 7 (start of good_function)
        definition_res = await consult_lsp.ainvoke({
            "action": 'find_definition',
            "file_path": abs_path,
            "line": 8,
            "character": 7
        })
        print(f"Definition Result: {definition_res}")
        # Expecting something like ".../temp_lsp_test.py:4"
        # We check ends_with because path might be full absolute path
        assert definition_res.strip().endswith(f"{filename}:4")

        # 3. Hover
        # Hover over "good_function" at line 8
        print("\n--- Testing Hover ---")
        hover_res = await consult_lsp.ainvoke({
            "action": 'hover',
            "file_path": abs_path,
            "line": 8,
            "character": 7
        })
        print(f"Hover Result: {hover_res}")
        # Expect docstring or signature
        # Pyright usually returns signature and sometimes docstring
        assert "Returns the square of x" in hover_res or "(x: int) -> int" in hover_res

        print("\n=== All LSP Capabilities Verified Successfully ===")

    finally:
        if os.path.exists(filename):
            os.remove(filename)

if __name__ == "__main__":
    asyncio.run(test_complete_lsp_capabilities())
