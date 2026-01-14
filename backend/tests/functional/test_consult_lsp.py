import asyncio
import os

import pytest

from app.domain.tools.coding.lsp import consult_lsp


@pytest.mark.asyncio
async def test_consult_lsp_errors():
    # Create a temporary file with error
    filename = "temp_error_test.py"
    content = "def foo() -> int:\n    return 'string'\n" # Type error

    # Write file
    with open(filename, "w") as f:
        f.write(content)

    abs_path = os.path.abspath(filename)
    print(f"Testing LSP on {abs_path}")

    try:
        # Give LSP a moment if it needs to start up (consult_lsp handles starting manager)
        # But verify result

        # First call might trigger server start
        result = await consult_lsp.ainvoke({"action": 'check_errors', "file_path": abs_path})
        print(f"Result 1: {result}")

        # If server was just starting, it might not have diagnostics yet?
        # PyrightServer waits for analysis complete.

        if "No errors found" in result:
             # Maybe wait and try again (LSP is async notification)
             await asyncio.sleep(2)
             result = await consult_lsp.ainvoke({"action": 'check_errors', "file_path": abs_path})
             print(f"Result 2: {result}")

        assert "Error" in result or "Warning" in result
        assert "Line 2" in result

    finally:
        if os.path.exists(filename):
            os.remove(filename)

if __name__ == "__main__":
    asyncio.run(test_consult_lsp_errors())
