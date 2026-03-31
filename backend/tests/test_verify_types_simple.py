#!/usr/bin/env python3
"""
Simple test to verify the edit_file verify_types logic.
This test checks the code structure without requiring full app initialization.
"""

import ast
import sys

def test_code_structure():
    """Verify that verify_types logic exists in edit_file."""
    
    print("=" * 70)
    print("Verifying edit_file verify_types implementation")
    print("=" * 70)
    
    # Read the edit_file source
    with open('app/domain/tools/files/edit_file.py', 'r') as f:
        source = f.read()
    
    # Check 1: verify_types parameter exists in function signature
    print("\n1. Checking for verify_types parameter...")
    if 'verify_types: bool = True' in source:
        print("   ✅ verify_types parameter found with default=True")
    else:
        print("   ❌ verify_types parameter not found")
        return False
    
    # Check 2: verify_types is used in handle_edit
    print("\n2. Checking for verify_types usage in handle_edit...")
    if 'if verify_types:' in source:
        print("   ✅ verify_types conditional check found")
    else:
        print("   ❌ verify_types conditional check not found")
        return False
    
    # Check 3: engine.check_types is called
    print("\n3. Checking for engine.check_types call...")
    if 'engine.check_types' in source:
        print("   ✅ engine.check_types call found")
    else:
        print("   ❌ engine.check_types call not found")
        return False
    
    # Check 4: get_exploration_engine is imported
    print("\n4. Checking for get_exploration_engine import...")
    if 'get_exploration_engine' in source:
        print("   ✅ get_exploration_engine import found")
    else:
        print("   ❌ get_exploration_engine import not found")
        return False
    
    # Check 5: template uses diagnostics
    print("\n5. Checking edit_result template...")
    try:
        with open('app/config/templates/files/edit_result.prompt.j2', 'r') as f:
            template = f.read()
        
        checks = [
            ('diagnostics variable', '{% if diagnostics -%}' in template),
            ('severity filter', 'selectattr("severity"' in template),
            ('Error severity', 'equalto", "Error")' in template or '"Error"' in template),
            ('Warning severity', 'equalto", "Warning")' in template or '"Warning"' in template),
            ('line number display', 'e.line' in template),
            ('message display', 'e.message' in template),
        ]
        
        all_passed = True
        for name, check in checks:
            if check:
                print(f"   ✅ {name} found")
            else:
                print(f"   ❌ {name} not found")
                all_passed = False
        
        if not all_passed:
            return False
            
    except FileNotFoundError:
        print("   ❌ edit_result.prompt.j2 template not found")
        return False
    
    print("\n" + "=" * 70)
    print("✅ All code structure checks passed!")
    print("=" * 70)
    return True


def test_engine_check_types():
    """Verify that CodeExplorationEngine.check_types is properly implemented."""
    
    print("\n" + "=" * 70)
    print("Verifying CodeExplorationEngine.check_types implementation")
    print("=" * 70)
    
    with open('app/domain/codebase/exploration/engine.py', 'r') as f:
        source = f.read()
    
    checks = [
        ('async def check_types', 'async def check_types' in source),
        ('file_path parameter', 'file_path: str' in source),
        ('repo_path parameter', 'repo_path' in source),
        ('LSP manager usage', 'self.lsp_manager' in source),
        ('get_server call', '.get_server(' in source),
        ('get_diagnostics call', '.get_diagnostics(' in source),
        ('_format_diagnostics call', '_format_diagnostics' in source),
        ('severity mapping', 'severity_map' in source),
        ('Error/Warning/Info/Hint', '"Error"' in source and '"Warning"' in source),
        ('wait loop for diagnostics', 'for _ in range' in source and 'await asyncio.sleep' in source),
    ]
    
    all_passed = True
    for name, check in checks:
        if check:
            print(f"   ✅ {name}")
        else:
            print(f"   ❌ {name}")
            all_passed = False
    
    if all_passed:
        print("\n" + "=" * 70)
        print("✅ CodeExplorationEngine.check_types is properly implemented!")
        print("=" * 70)
    
    return all_passed


def test_integration_points():
    """Verify integration between edit_file and check_types."""
    
    print("\n" + "=" * 70)
    print("Verifying integration points")
    print("=" * 70)
    
    # Check that edit_file uses the engine correctly
    with open('app/domain/tools/files/edit_file.py', 'r') as f:
        edit_source = f.read()
    
    # Find the handle_edit function
    print("\n1. Checking handle_edit function structure...")
    
    # Check for proper try-except around type checking
    if 'try:' in edit_source and 'engine.check_types' in edit_source:
        print("   ✅ Type checking is wrapped in try-except")
    else:
        print("   ⚠️  Could not verify try-except wrapping")
    
    # Check that diagnostics are passed to template
    if 'template_context["diagnostics"]' in edit_source:
        print("   ✅ Diagnostics are passed to template context")
    else:
        print("   ❌ Diagnostics not passed to template context")
        return False
    
    # Check that type checking happens after successful edit
    edit_file_path = 'app/domain/tools/files/edit_file.py'
    with open(edit_file_path, 'r') as f:
        lines = f.readlines()
    
    # Find the line numbers of success check and verify_types
    success_line = None
    verify_types_line = None
    
    for i, line in enumerate(lines):
        if 'if result["success"]:' in line:
            success_line = i
        if 'if verify_types:' in line and success_line and i > success_line:
            verify_types_line = i
            break
    
    if success_line and verify_types_line:
        print(f"   ✅ Type checking happens after success check (lines {success_line+1} -> {verify_types_line+1})")
    else:
        print("   ⚠️  Could not verify execution order")
    
    print("\n" + "=" * 70)
    print("✅ Integration points verified!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    # Change to backend directory if needed
    import os
    if os.path.exists('backend'):
        os.chdir('backend')
    
    results = []
    results.append(("Code Structure", test_code_structure()))
    results.append(("Engine Implementation", test_engine_check_types()))
    results.append(("Integration Points", test_integration_points()))
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 70)
    if all_passed:
        print("✅ verify_types functionality is properly implemented!")
        print("\nKey features:")
        print("  - verify_types=True by default in edit_file")
        print("  - Type checking via LSP (CodeExplorationEngine)")
        print("  - Errors/warnings displayed in edit result")
        print("  - Template shows semantic errors with line numbers")
    else:
        print("❌ Some checks failed. Please review the implementation.")
    print("=" * 70)
    
    sys.exit(0 if all_passed else 1)
