from app.domain.tools.dynamic import create_python_tool

def test_security():
    print("Testing Dynamic Tool Security...")

    # Test 1: Import OS (Should Fail)
    unsafe_code_os = """
import os
def hack():
    os.system('echo hacked')
"""
    result = create_python_tool.invoke({"name": "unsafe_os", "description": "test", "code": unsafe_code_os})
    if "Security Error" in result and "Import forbidden: 'os'" in result:
        print("✅ PASS: 'import os' blocked.")
    else:
        print(f"❌ FAIL: 'import os' check failed. Result: {result}")

    # Test 2: Eval (Should Fail)
    unsafe_code_eval = """
def calc(x):
    return eval(x)
"""
    result = create_python_tool.invoke({"name": "unsafe_eval", "description": "test", "code": unsafe_code_eval})
    if "Security Error" in result and "Function call forbidden: 'eval()'" in result:
         print("✅ PASS: 'eval()' blocked.")
    else:
         print(f"❌ FAIL: 'eval()' check failed. Result: {result}")

    # Test 3: Safe Code (Should Pass)
    safe_code = """
import json
import math
def add(a: int, b: int) -> int:
    "Adds two numbers"
    return a + b
"""
    result = create_python_tool.invoke({"name": "safe_calc", "description": "test", "code": safe_code})
    if "Success" in result:
        print("✅ PASS: Safe code allowed.")
    else:
         print(f"❌ FAIL: Safe code rejected. Result: {result}")

if __name__ == "__main__":
    test_security()
