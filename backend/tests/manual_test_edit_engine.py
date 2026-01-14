import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.domain.tools.utils.editing.engine import EditEngine

original_content = """
def hello_world():
    print("Hello")
    print("World")

def calculate(a, b):
    # This is a calculation
    return a + b
"""

# Case 1: Wrong Indentation Target
messy_target_indent = """
  def calculate(a, b):
      # This is a calculation
      return a + b
"""
# Note: Original had 0 indent for def, 4 for body. Messy has 2 for def, 6 for body.

# Case 2: Extra Newlines Target
messy_target_newlines = """
def hello_world():

    print("Hello")
    print("World")
"""

replacement = """def MATCHED_AND_REPLACED():
    return "Success"
"""

print("--- Test 1: Wrong Indentation ---")
# Strategy 'IndentationFlexibleReplacer' not implemented yet?
# Wait, I implemented: Simple, LineTrimmed, BlockAnchor, WhitespaceNormalized.
# LineTrimmed should handle "extra indentation" if it's consistent?
# LineTrimmed ignores leading whitespace PER LINE. So yes, it should match content regardless of indent.
# BUT, IndentationFlexibleReplacer in Opencode is smarter (re-indents).
# Let's see if LineTrimmed works for this case.

success, new_content, log = EditEngine.apply_replacement(original_content, messy_target_indent, replacement)
print(f"Success: {success}")
print(f"Log: {log}")
if success:
    print("New Content snippet:")
    print(new_content)

print("\n--- Test 2: Extra Newlines ---")
# WhitespaceNormalizedReplacer should handle this if newlines count as whitespace (they do in my simple ' '.join() impl)
success, new_content, log = EditEngine.apply_replacement(original_content, messy_target_newlines, replacement)
print(f"Success: {success}")
print(f"Log: {log}")
if success:
    print("New Content snippet:")
    print(new_content)
