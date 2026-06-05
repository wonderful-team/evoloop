#!/usr/bin/env python3.10
import asyncio, sys, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.tools.files.list_dir import list_dir

async def _test_dir_impl(path, tree=False, depth=1, filter_pattern=None):
    print(f"\n{'='*60}")
    print(f"[TEST] list_dir")
    print(f"  path={path}")
    print(f"  tree={tree}, depth={depth}, filter={filter_pattern}")
    print('='*60)
    
    start = time.perf_counter()
    result = await list_dir.ainvoke({
        "path": path,
        "tree": tree,
        "depth": depth,
        "filter": filter_pattern,
        "stats": True,
    })
    elapsed = (time.perf_counter() - start) * 1000
    
    lines = result.split('\n')
    non_empty = [l for l in lines if l.strip()]
    total_lines = len(lines)
    
    print(f"\n[OUTPUT first 800 chars]\n{result[:800]}")
    if len(result) > 800:
        print(f"\n... ({len(result) - 800} more chars)")
    
    print(f"\n[STATS]")
    print(f"  Total chars: {len(result)}")
    print(f"  Total lines: {total_lines}")
    print(f"  Non-empty lines: {len(non_empty)}")
    print(f"  Time: {elapsed:.2f} ms")
    
    # Check truncation
    truncated = any("more entries hidden" in l for l in lines)
    if truncated:
        print(f"  ⚠️ Truncated")
    else:
        print(f"  ✅ Full output (no truncation)")
    
    return result

async def main():
    # 1. 单层大量文件: alembic/versions (52 migration files)
    await _test_dir_impl(
        str(PROJECT_ROOT / "app" / "alembic" / "versions"),
        tree=True, depth=1
    )
    
    # 2. 多层大量文件: tests/ (162 entries)
    await _test_dir_impl(
        str(PROJECT_ROOT / "tests"),
        tree=True, depth=2
    )
    
    # 3. 超大深度: tests/ depth=3
    await _test_dir_impl(
        str(PROJECT_ROOT / "tests"),
        tree=True, depth=3
    )
    
    # 4. 过滤测试: tests/ 下所有 *.py
    await _test_dir_impl(
        str(PROJECT_ROOT / "tests"),
        tree=False, filter_pattern="*.py"
    )
    
    print("\n" + "="*60)
    print("ALL TESTS COMPLETE")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
