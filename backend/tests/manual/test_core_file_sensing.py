import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from app.core import file as file_utils

async def test_sensing_and_utils():
    print("--- Testing Core File Sensing & Utils ---")
    
    # 1. Test Path Utilities
    print("\n[1] Testing Path Utils...")
    base = tempfile.gettempdir()
    safe_path = file_utils.safe_join(base, "evoloop_test.txt")
    print(f"Safe Join: {safe_path}")
    assert safe_path.startswith(os.path.abspath(base))
    
    try:
        file_utils.safe_join(base, "../unsafe.txt")
    except ValueError:
        print("Path Traversal Protection: OK")
        
    sanitized = file_utils.sanitize_filename("test/file:name*.txt")
    print(f"Sanitized Filename: {sanitized}")
    assert "/" not in sanitized and "*" not in sanitized

    # 2. Test Hashing
    print("\n[2] Testing Hashing...")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello evoloop")
        tmp_name = f.name
    
    try:
        md5_file = file_utils.compute_file_hash(tmp_name)
        print(f"File MD5: {md5_file}")
        assert len(md5_file) > 0
        
        content_md5 = file_utils.compute_md5("hello evoloop")
        print(f"Content MD5: {content_md5}")
        assert len(content_md5) == 32
    finally:
        os.remove(tmp_name)

    # 3. Test MIME & Category
    print("\n[3] Testing MIME & Category...")
    test_cases = [
        ("test.py", "text/x-python", "code"),
        ("test.md", "text/markdown", "document"),
        ("test.png", "image/png", "image"),
        ("test.xyz", "application/octet-stream", "text")
    ]
    
    for filename, expected_mime, expected_cat in test_cases:
        mime = file_utils.guess_mime_type(filename)
        cat = file_utils.get_file_category(filename)
        print(f"Testing {filename}: got MIME={mime}, Category={cat} | Expected MIME={expected_mime}, Category={expected_cat}")
        assert cat == expected_cat

    # 4. Test Tree Traversal (walk_tree)
    print("\n[4] Testing Tree Traversal...")
    temp_dir = tempfile.mkdtemp()
    try:
        # Create some files
        os.makedirs(os.path.join(temp_dir, "src"))
        Path(os.path.join(temp_dir, "src", "main.py")).touch()
        Path(os.path.join(temp_dir, "README.md")).touch()
        os.makedirs(os.path.join(temp_dir, ".git"))
        Path(os.path.join(temp_dir, ".git", "config")).touch()
        
        found_files = []
        for p in file_utils.walk_tree(temp_dir):
            found_files.append(os.path.relpath(p, temp_dir))
            
        print(f"Found Files: {found_files}")
        assert "src/main.py" in found_files
        assert "README.md" in found_files
        assert ".git/config" not in found_files  # Should be ignored by default
    finally:
        shutil.rmtree(temp_dir)

    print("\n--- ALL SENSING & UTILS TESTS PASSED ---")

if __name__ == "__main__":
    asyncio.run(test_sensing_and_utils())
