import asyncio
import os
import sys
from pathlib import Path

# Fix python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.core.tools.base import get_working_directory
from app.domain.tools.coding.lsp import consult_lsp
from app.infrastructure.config.service import SystemConfigService

async def test_lsp_path_resolution():
    # 1. Test get_working_directory fallback
    wd = get_working_directory()
    print(f"Detected Working Directory (Fallback): {wd}")
    
    db_root = SystemConfigService.get_value("WORKSPACE_ROOT")
    print(f"SystemConfig WORKSPACE_ROOT: {db_root}")
    
    # 2. Test consult_lsp relative path
    # We'll use a real file but pass a relative path
    test_file = "xianyu-crawler/crawler.py"
    # The user's log showed it failed on this file
    
    print(f"\nTesting consult_lsp with: {test_file}")
    
    # We'll mock the server call or just let it fail at the core logic if server not running,
    # but the goal is to see if it even finds the file and calculates the right repo_root.
    
    # Note: This might still return 'Error' if the server doesn't start, 
    # but it shouldn't be 'FileNotFoundError' at the resolve step.
    result = await consult_lsp.ainvoke({"action": "check_errors", "file_path": test_file})
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(test_lsp_path_resolution())
