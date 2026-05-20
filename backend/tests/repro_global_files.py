import os
import sys
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.core.context import ContextManager
from app.domain.tools.files.utils import resolve_and_validate_path
from app.domain.tools.files.list_directory import handle_list
from app.infrastructure.config.service import SystemConfigService


async def diagnose():
    print("=== Configuration Diagnosis ===")
    print(f"APP_DATA_DIR:      {settings.APP_DATA_DIR}")
    print(f"UPLOAD_DIR (env):  {settings.UPLOAD_DIR}")
    print(f"CHAT_UPLOAD_DIR:   {settings.CHAT_UPLOAD_DIR}")
    print(f"ALLOWED_PREFIXES:  {settings.ALLOWED_PATH_PREFIXES}")
    workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
    print(f"WORKSPACE_ROOT:    {workspace_root}")
    print()

    # Prepare test file
    test_file = "repro_test_file.txt"
    test_file_path = os.path.join(settings.CHAT_UPLOAD_DIR, test_file)
    os.makedirs(settings.CHAT_UPLOAD_DIR, exist_ok=True)
    with open(test_file_path, "w") as f:
        f.write("Reproduction test content")
    print(f"Created test file: {test_file_path}")
    print()

    print("=== Test 1: Explicit uploads/ prefix (Global Mode) ===")
    ctx = ContextManager.current()
    ctx.project_id = 0
    r1 = await resolve_and_validate_path(f"uploads/{test_file}")
    print(f"  Input:    uploads/{test_file}")
    print(f"  Resolved: {r1}")
    print(f"  {'✅ Correct' if r1 == test_file_path else '❌ Wrong'}")
    print()

    print("=== Test 2: Explicit uploads/ prefix (Project Mode) ===")
    ctx.project_id = 43
    r2 = await resolve_and_validate_path(f"uploads/{test_file}")
    print(f"  Input:    uploads/{test_file}")
    print(f"  Resolved: {r2}")
    print(f"  {'✅ Correct (same location)' if r2 == test_file_path else '❌ Wrong'}")
    print()

    print("=== Test 3: Smart Fallback — no uploads/ prefix (Global Mode) ===")
    ctx.project_id = 0
    r3 = await resolve_and_validate_path(test_file)
    print(f"  Input:    {test_file} (no prefix)")
    print(f"  Resolved: {r3}")
    print(f"  {'✅ Fallback works' if r3 == test_file_path else '❌ Fallback failed'}")
    print()

    print("=== Test 4: list_directory root — uploads/ virtual injection ===")
    ctx.project_id = 0
    res, meta = await handle_list(path=".", tree=False)
    has_uploads = "uploads/" in res
    print(f"  uploads/ visible in listing: {'✅ Yes' if has_uploads else '❌ No'}")
    print(f"  First few lines: {res.splitlines()[:4]}")
    print()

    print("=== Summary ===")
    all_ok = (r1 == test_file_path and r2 == test_file_path and r3 == test_file_path and has_uploads)
    print("✅ All tests passed!" if all_ok else "❌ Some tests failed.")


if __name__ == "__main__":
    asyncio.run(diagnose())
