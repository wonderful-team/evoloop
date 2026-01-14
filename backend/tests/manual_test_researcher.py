import os
import sys

# Fix path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.tools.registry_utils import get_node_tools


def test_researcher_tools():
    print("--- Test: Researcher Tools ---")
    tools = get_node_tools("researcher")
    tool_names = [t.name for t in tools]

    print(f"Tools loaded: {tool_names}")

    if "crawl_url" in tool_names:
        print("SUCCESS: crawl_url found.")
    else:
        print("FAIL: crawl_url NOT found.")

    if "search_web" in tool_names:
        print("SUCCESS: search_web found.")
    else:
        print("WARNING: search_web not found (expected if no provider configured currently, or import failed).")

if __name__ == "__main__":
    test_researcher_tools()
