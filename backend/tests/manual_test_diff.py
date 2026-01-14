import os
import sys

# Fix path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.memory.diff import diff_tracker


def test_diff_tracker():
    print("\n--- Test: Diff Tracker ---")

    test_file = "test_diff_target.txt"

    # 1. Setup Initial File
    with open(test_file, "w") as f:
        f.write("Line 1\nLine 2\nLine 3\n")

    print(f"Created {test_file} with initial content.")

    # 2. Capture Snapshot
    print("Capturing snapshot...")
    diff_tracker.capture_snapshot(os.path.abspath(test_file))

    # 3. Modify File
    print("Modifying file...")
    with open(test_file, "w") as f:
        f.write("Line 1\nLine 2 (Modified)\nLine 3\nLine 4 (New)\n")

    # 4. Compute Diff
    print("Computing diff...")
    diff = diff_tracker.compute_diff(os.path.abspath(test_file))

    print("\n--- Generated Diff ---")
    print(diff)
    print("----------------------")

    if "-Line 2" in diff and "+Line 2 (Modified)" in diff and "+Line 4 (New)" in diff:
        print("SUCCESS: Diff accurately reflects changes.")
    else:
        print("FAIL: Diff incorrect or empty.")

    # Cleanup
    os.remove(test_file)

if __name__ == "__main__":
    test_diff_tracker()
