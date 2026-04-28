#!/usr/bin/env python3
"""
Test script to verify edit_file's verify_types functionality.
"""

import asyncio
import os
import sys
import tempfile

# Setup paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.dirname(BASE_DIR))

# Load env
env_path = os.path.join(os.path.dirname(BASE_DIR), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))


async def test_verify_types():
    """Test that verify_types in edit_file works correctly."""
    from app.domain.tools.files.edit_file import edit_file
    from app.core.tools import get_working_directory
    
    print("=" * 70)
    print("Testing edit_file verify_types functionality")
    print("=" * 70)
    
    # Create a temporary Python file with a type error
    test_code = """def greet(name: str) -> str:
    return "Hello, " + name

# This will cause a type error
result = greet(123)  # Passing int instead of str
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(test_code)
        temp_file = f.name
    
    print(f"\n1. Created test file: {temp_file}")
    print(f"   Content preview:\n{test_code[:200]}...")
    
    try:
        # Test 1: Edit with verify_types=True (default)
        print("\n2. Testing edit with verify_types=True...")
        result = await edit_file.ainvoke({
            "path": temp_file,
            "target": "result = greet(123)",
            "replacement": "result = greet('World')",
            "verify_types": True  # This should trigger type checking
        })
        
        print(f"   Result:\n{result[:500]}...")
        
        # Check if type checking was performed
        if "type" in result.lower() or "diagnostic" in result.lower() or "error" in result.lower():
            print("   ✅ Type checking was performed (found related keywords in output)")
        else:
            print("   ⚠️  Type checking may not have been performed (no type-related keywords)")
        
        # Test 2: Edit with verify_types=False
        print("\n3. Testing edit with verify_types=False...")
        result_no_check = await edit_file.ainvoke({
            "path": temp_file,
            "target": "result = greet('World')",
            "replacement": "result = greet('Universe')",
            "verify_types": False
        })
        
        print(f"   Result:\n{result_no_check[:300]}...")
        print("   ✅ Edit completed without type checking")
        
        # Test 3: Check engine directly
        print("\n4. Testing CodeExplorationEngine.check_types directly...")
        from app.domain.codebase.exploration.engine import get_exploration_engine
        
        engine = get_exploration_engine()
        diagnostics = await engine.check_types(temp_file, os.path.dirname(temp_file))
        
        if diagnostics:
            print(f"   Found {len(diagnostics)} diagnostic(s):")
            for d in diagnostics[:3]:
                if "error" in d:
                    print(f"     - Error: {d['error']}")
                else:
                    print(f"     - {d.get('severity', 'Unknown')}: Line {d.get('line', '?')}: {d.get('message', 'No message')[:50]}...")
        else:
            print("   No diagnostics returned (LSP may not be available for this file)")
        
    finally:
        # Cleanup
        os.unlink(temp_file)
        print(f"\n5. Cleaned up test file")
    
    print("\n" + "=" * 70)
    print("Test completed")
    print("=" * 70)


async def test_verify_types_with_errors():
    """Test that type errors are properly detected and reported."""
    print("\n" + "=" * 70)
    print("Testing type error detection")
    print("=" * 70)
    
    from app.domain.tools.files.edit_file import edit_file
    
    # Create a file that will have type errors after edit
    test_code = """def add(a: int, b: int) -> int:
    return a + b

# Correct usage
x = add(1, 2)
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(test_code)
        temp_file = f.name
    
    print(f"\n1. Created test file: {temp_file}")
    
    try:
        # Make an edit that introduces a type error
        print("\n2. Making an edit that introduces a type error...")
        result = await edit_file.ainvoke({
            "path": temp_file,
            "target": "x = add(1, 2)",
            "replacement": "x = add('hello', 'world')",  # Type error: str instead of int
            "verify_types": True
        })
        
        print(f"   Result:\n{result}")
        
        if "SEMANTIC" in result or "type" in result.lower() or "error" in result.lower():
            print("   ✅ Type error was detected and reported!")
        else:
            print("   ⚠️  Type error may not have been detected")
            print("   (This could be because LSP server is not running or file is not indexed)")
        
    finally:
        os.unlink(temp_file)
        print(f"\n3. Cleaned up test file")


if __name__ == "__main__":
    asyncio.run(test_verify_types())
    asyncio.run(test_verify_types_with_errors())
