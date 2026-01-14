import os
import sys

# Add backend to path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.domain.tools.utils.editing.engine import EditEngine

print("--- Test: Advanced Edit Engine Strategies ---")

# Case 1: Trimmed Boundary
# Old content has spaces around a block that user provides without spaces
content_trimmed = """
    def my_function():
        return True
"""
target_trimmed = """def my_function():
    return True
"""
# TrimmedBoundaryReplacer should match this by seeing that target.trim() == content.trim()

success, res, log = EditEngine.apply_replacement(content_trimmed, target_trimmed, "NEW_CODE")
print(f"Test 1 (TrimmedBoundary): {success} -> {log}")

# Case 2: Escape Normalization
# Content has real newlines, User provides \\n literal
content_escape = "line1\nline2"
target_escape = "line1\\nline2"

success, res, log = EditEngine.apply_replacement(content_escape, target_escape, "NEW_CODE")
print(f"Test 2 (EscapeNormalized): {success} -> {log}")

# Case 3: Context Aware
# A long block where middle lines have slight errors, but anchors match
content_context = """
class User:
    def __init__(self):
        self.name = "John"
        self.age = 30
        self.role = "Admin"
    
    def save(self):
        print("Saving")
"""

# User provides block with typo in middle ('self.age = 31')
target_context = """class User:
    def __init__(self):
        self.name = "John"
        self.age = 31
        self.role = "Admin"
    
    def save(self):
        print("Saving")
"""
# BlockAnchorReplacer might fail if diff is too big? Or ContextAware uses different logic.
# ContextAwareReplacer splits by lines and uses first/last line of FIND as anchors.
# Anchor for target_context: "class User:" and "        print("Saving")" (last non-empty)

success, res, log = EditEngine.apply_replacement(content_context, target_context, "NEW_CODE")
print(f"Test 3 (ContextAware): {success} -> {log}")
