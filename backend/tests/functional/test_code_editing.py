import os

import pytest

from app.domain.tools.files.actions.edit import handle_edit

TEST_FILE = "fuzzy_test_target.py"

ORIGINAL_CONTENT = """def hello():
    print("Hello World")
    print("This is a test")
    
def goodbye():
    print("Goodbye")
"""

@pytest.mark.asyncio
async def test_fuzzy_editing():
    try:
        # Setup
        with open(TEST_FILE, "w") as f:
            f.write(ORIGINAL_CONTENT)

        print(f"Created {TEST_FILE}")

        # 1. Test Exact Match (Baseline)
        print("\\n--- Test 1: Exact Match ---")
        target_exact = """def goodbye():
    print("Goodbye")"""

        replacement_exact = """def goodbye():
    print("Au Revoir")"""

        res = await handle_edit(TEST_FILE, target=target_exact, content=replacement_exact)
        print(f"Result: {res}")
        assert "Successfully updated" in res

        with open(TEST_FILE) as f:
            content = f.read()
        assert "Au Revoir" in content

        # Reset
        with open(TEST_FILE, "w") as f: f.write(ORIGINAL_CONTENT)

        # 2. Test Fuzzy Match (Whitespace/Indentation Hallucination)
        print("\\n--- Test 2: Fuzzy Match (Whitespace) ---")
        # LLM "hallucinates" 4 spaces instead of tabs, or misses a newline
        # The original has 4 spaces. Let's try matching with different indent in target string
        # Actually, let's try strict mismatch.

        # Target has 2 spaces indent, file has 4
        target_fuzzy_indent = """def hello():
  print("Hello World")
  print("This is a test")"""

        replacement_fuzzy = """def hello():
    print("Hello Fuzzy World")
    print("Fuzzy Logic Works")"""

        res = await handle_edit(TEST_FILE, target=target_fuzzy_indent, content=replacement_fuzzy)
        print(f"Result: {res}")

        # We expect Success via Fuzzy
        assert "Successfully updated" in res
        assert "Fuzzy Match" in res

        with open(TEST_FILE) as f:
            content = f.read()
        assert "Hello Fuzzy World" in content

        # 3. Test Fuzzy Match (Missing Lines / Partial)
        # This tests difflib robustness
        print("\\n--- Test 3: Fuzzy Match (Partial/Hallucinated Lines) ---")
        with open(TEST_FILE, "w") as f: f.write(ORIGINAL_CONTENT)

        # Target context is slightly wrong (e.g. wrong print message)
        target_hallucinated = """def hello():
    print("Hello Universe") 
    print("This is a test")"""
    # "Universe" vs "World" -> Mismatch

        res = await handle_edit(TEST_FILE, target=target_hallucinated, content=replacement_fuzzy)
        print(f"Result: {res}")

        # Depending on threshold, this might pass or fail.
        # Our threshold is 0.8. "World" vs "Universe" is close enough in context of block?
        # Let's see.

    finally:
        if os.path.exists(TEST_FILE):
             os.remove(TEST_FILE)

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_fuzzy_editing())
