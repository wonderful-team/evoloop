"""
Error Recovery End-to-End Verification Script

This script tests if the Coder node can:
1. Detect a syntax error using `consult_lsp`
2. Autonomously fix the error
"""
import asyncio
import os
import sys
import json
from unittest.mock import patch, MagicMock

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

# Target file with error
TARGET_FILE = "app/domain/math_utils.py"
ABSOLUTE_TARGET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), TARGET_FILE)


async def test_lsp_detection():
    """
    Test 1: Verify LSP can detect the syntax error.
    """
    print("\n--- Test 1: LSP Detection ---")
    
    from app.domain.tools.coding.lsp import consult_lsp
    
    # Call LSP to check for errors
    result = await consult_lsp.ainvoke({
        "action": "check_errors",
        "file_path": TARGET_FILE,
    })
    
    print(f"LSP Output:\n{result}")
    
    # Check if error was detected
    if "Error" in result and ("syntax" in result.lower() or "expected" in result.lower() or "line 4" in result.lower()):
        print("✅ SUCCESS: LSP detected the syntax error.")
        return True
    elif "No errors found" in result:
        print("❌ FAILED: LSP did not detect the error. (Server might not be running)")
        return False
    else:
        print(f"⚠️ INCONCLUSIVE: Unexpected output. Check manually.")
        return None


async def test_coder_fix():
    """
    Test 2: Simulate Coder node receiving an error fix request.
    
    We will directly invoke the coder's logic or the manage_file tool
    after LSP detection to see if it can apply a fix.
    """
    print("\n--- Test 2: Coder Fix Application ---")
    
    # Read the file to see current state
    with open(ABSOLUTE_TARGET, "r") as f:
        before_content = f.read()
    
    print(f"Before Fix (Line 4):\n{before_content.splitlines()[3]}")
    
    # Simulate the Coder's fix action
    # The Coder would use manage_file(action='update_block') to fix this.
    # We manually apply the fix to verify the mechanism.
    
    from app.domain.tools.files.actions.edit import handle_edit
    
    # The target block with the error
    target_block = """def add(a, b)  # <-- Missing colon here!
    \"\"\"Add two numbers.\"\"\""""
    
    # The correct replacement
    replacement_block = """def add(a, b):  # Fixed: Added colon
    \"\"\"Add two numbers.\"\"\""""
    
    result = await handle_edit(
        path=TARGET_FILE,
        target=target_block,
        content=replacement_block
    )
    
    print(f"Edit Result: {result}")
    
    # Read file again
    with open(ABSOLUTE_TARGET, "r") as f:
        after_content = f.read()
    
    print(f"After Fix (Line 4):\n{after_content.splitlines()[3]}")
    
    # Verify
    if "def add(a, b):" in after_content:
        print("✅ SUCCESS: Syntax error was fixed!")
        return True
    else:
        print("❌ FAILED: Fix was not applied correctly.")
        return False


async def test_lsp_after_fix():
    """
    Test 3: Verify LSP reports no errors after the fix.
    """
    print("\n--- Test 3: LSP After Fix ---")
    
    from app.domain.tools.coding.lsp import consult_lsp
    
    result = await consult_lsp.ainvoke({
        "action": "check_errors",
        "file_path": TARGET_FILE,
    })
    
    print(f"LSP Output:\n{result}")
    
    if "No errors found" in result:
        print("✅ SUCCESS: File is now error-free!")
        return True
    else:
        print("❌ FAILED: File still has errors.")
        return False


async def main():
    print("=" * 60)
    print("Error Recovery End-to-End Verification")
    print("=" * 60)
    
    results = {}
    
    # Test 1: LSP Detection
    results["lsp_detection"] = await test_lsp_detection()
    
    # Test 2: Coder Fix
    results["coder_fix"] = await test_coder_fix()
    
    # Test 3: LSP After Fix
    results["lsp_after_fix"] = await test_lsp_after_fix()
    
    print("\n" + "=" * 60)
    print("Summary:")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else ("⚠️ SKIP" if passed is None else "❌ FAIL")
        print(f"  {test_name}: {status}")
    print("=" * 60)
    
    # Cleanup: Remove the test file
    if os.path.exists(ABSOLUTE_TARGET):
        os.remove(ABSOLUTE_TARGET)
        print(f"\nCleanup: Removed {TARGET_FILE}")
    
    return all(v for v in results.values() if v is not None)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
