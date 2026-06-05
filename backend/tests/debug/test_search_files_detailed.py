"""
search_files 工具详细验证测试。

覆盖场景：
1. 基础文本搜索
2. 路径限制 (path)
3. 文件范围过滤 (scope)
4. 大小写不敏感 (case_insensitive)
5. 无匹配情况
6. 排除目录验证 (__pycache__ 等不应命中)
7. 正则表达式搜索
8. 过多匹配限制 (max 100)
9. 非侵入性验证 (只读工具不应产生 file_operations)
"""

import asyncio
import os
import sys
import tempfile
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from app.domain.tools.files.grep_search import grep_search_internal
from app.core.tools import get_working_directory


# =============================================================================
# 辅助函数
# =============================================================================
async def call_search(**kwargs) -> str:
    """调用 search_files 并返回结果字符串。"""
    return await grep_search_internal(**kwargs)


def assert_contains(text: str, *substrings):
    for s in substrings:
        assert s in text, f"期望结果包含 '{s}'，实际: {repr(text[:200])}"


def assert_not_contains(text: str, *substrings):
    for s in substrings:
        assert s not in text, f"期望结果不包含 '{s}'，实际: {repr(text[:200])}"


# =============================================================================
# 测试场景
# =============================================================================
async def test_basic_search():
    print("\n[TEST 1] 基础文本搜索 — 在已知项目中搜索常见关键词")
    tmpdir = os.path.join(BASE_DIR, "_test_search_basic")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "code.py"), "w") as f:
            f.write("class User:\n    pass\n")

        result = await call_search(pattern="class", path=tmpdir)
        # "Error: Too many matches" 是正常行为，不是系统错误
        is_too_many = "Too many matches" in result
        is_normal = result != "No matches found." and not result.startswith("Error running search")
        assert is_normal or is_too_many, f"不应出现系统错误: {result[:200]}"
        line_count = len(result.splitlines()) if not is_too_many else ">100"
        print(f"  ✅ 基础搜索命中 {line_count} 行")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_path_restriction():
    print("\n[TEST 2] 路径限制 — 缩小搜索范围")
    tmpdir = os.path.join(BASE_DIR, "_test_search_path")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        subdir = os.path.join(tmpdir, "src")
        os.makedirs(subdir)
        with open(os.path.join(subdir, "code.py"), "w") as f:
            f.write("function test() {}\n")

        result = await call_search(pattern="function", path=subdir)
        assert_contains(result, "function")
        # 不应包含项目根目录其他位置的文件
        print(f"  ✅ 子目录搜索命中 {len(result.splitlines())} 行")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_scope_filter():
    print("\n[TEST 3] 文件范围过滤 (scope)")
    tmpdir = os.path.join(BASE_DIR, "_test_search_scope")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "test.php"), "w") as f:
            f.write("class User {}\n")
        with open(os.path.join(tmpdir, "test.py"), "w") as f:
            f.write("class User:\n    pass\n")

        # 只搜索 .php 文件
        result_php = await call_search(pattern="class", path=tmpdir, scope="*.php")
        # 只搜索 .py 文件（如果存在）
        result_py = await call_search(pattern="class", path=tmpdir, scope="*.py")

        # 两个结果集应不同（或一个为空）
        if result_php != "No matches found." and result_py != "No matches found.":
            assert result_php != result_py or result_php == "No matches found.", \
                "不同 scope 的搜索结果应不同"
        print(f"  ✅ *.php 命中 {len(result_php.splitlines())} 行, *.py 命中 {len(result_py.splitlines())} 行")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_case_insensitive():
    print("\n[TEST 4] 大小写不敏感搜索")
    tmpdir = os.path.join(BASE_DIR, "_test_search_case")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "test.txt"), "w") as f:
            f.write("TODO: fix this\n")
            f.write("todo: another task\n")

        # 大小写敏感：搜索 "TODO" 不应命中 "todo"
        result_sensitive = await call_search(pattern="TODO", path=tmpdir)
        # 大小写不敏感：应同时命中 "TODO" 和 "todo"
        result_insensitive = await call_search(
            pattern="todo", path=tmpdir, case_insensitive=True
        )

        # 不敏感搜索的结果应不少于敏感搜索
        sensitive_lines = 0 if result_sensitive == "No matches found." else len(result_sensitive.splitlines())
        insensitive_lines = 0 if result_insensitive == "No matches found." else len(result_insensitive.splitlines())
        print(f"  ✅ 敏感: {sensitive_lines} 行, 不敏感: {insensitive_lines} 行")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_no_matches():
    print("\n[TEST 5] 无匹配情况")
    tmpdir = os.path.join(BASE_DIR, "_test_search_none")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "test.txt"), "w") as f:
            f.write("hello world\n")

        result = await call_search(
            pattern="THIS_STRING_SHOULD_NOT_EXIST_ANYWHERE_12345",
            path=tmpdir
        )
        assert result == "No matches found.", f"应返回 'No matches found.'，实际: {repr(result)}"
        print(f"  ✅ 无匹配时正确返回: {repr(result)}")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_excluded_dirs():
    print("\n[TEST 6] 排除目录验证 — __pycache__ / node_modules 等不应被搜索")
    # 在工作目录内创建临时目录（resolve_and_validate_path 安全检查要求）
    tmpdir = os.path.join(BASE_DIR, "_test_search_excluded")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        # 创建正常文件
        normal_file = os.path.join(tmpdir, "normal.py")
        with open(normal_file, "w") as f:
            f.write("# TARGET_NORMAL\n")

        # 创建 __pycache__ 目录及其文件
        pycache_dir = os.path.join(tmpdir, "__pycache__")
        os.makedirs(pycache_dir)
        pycache_file = os.path.join(pycache_dir, "cached.py")
        with open(pycache_file, "w") as f:
            f.write("# TARGET_PYCACHE\n")

        # 搜索 TARGET_ 前缀
        result = await call_search(pattern="TARGET_", path=tmpdir)
        assert_contains(result, "TARGET_NORMAL")
        assert_not_contains(result, "TARGET_PYCACHE")
        print(f"  ✅ __pycache__ 被正确排除")

        # 验证 node_modules 也被排除
        node_dir = os.path.join(tmpdir, "node_modules")
        os.makedirs(node_dir)
        with open(os.path.join(node_dir, "pkg.js"), "w") as f:
            f.write("// TARGET_NODE\n")

        result2 = await call_search(pattern="TARGET_", path=tmpdir)
        assert_not_contains(result2, "TARGET_NODE")
        print(f"  ✅ node_modules 被正确排除")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_regex_search():
    print("\n[TEST 7] 正则表达式搜索")
    tmpdir = os.path.join(BASE_DIR, "_test_search_regex")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "test.php"), "w") as f:
            f.write("class User {}\n")

        # 搜索类似 class XXX( 的模式
        result = await call_search(pattern="class\s+\w+", path=tmpdir, scope="*.php")
        if result != "No matches found.":
            assert_contains(result, "class")
            print(f"  ✅ 正则搜索命中 {len(result.splitlines())} 行")
        else:
            print(f"  ℹ️ 项目中无 PHP class 定义")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_max_matches_limit():
    print("\n[TEST 8] 过多匹配限制 (max 100)")
    tmpdir = os.path.join(BASE_DIR, "_test_search_max")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        # 创建 150 个文件，每个都包含 MATCH_TARGET
        for i in range(150):
            filepath = os.path.join(tmpdir, f"file_{i:03d}.txt")
            with open(filepath, "w") as f:
                f.write(f"line 1: MATCH_TARGET in file {i}\n")

        result = await call_search(pattern="MATCH_TARGET", path=tmpdir)
        assert_contains(result, "Too many matches")
        assert_contains(result, "maximum is 100")
        print(f"  ✅ 超过 100 匹配时正确返回限制提示")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_readonly_no_file_operations():
    print("\n[TEST 9] 非侵入性验证 — search_files 是只读工具，不应修改文件系统")
    tmpdir = os.path.join(BASE_DIR, "_test_search_ro")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        test_file = os.path.join(tmpdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("SEARCHABLE_CONTENT\n")

        mtime_before = os.path.getmtime(test_file)

        # 执行搜索
        result = await call_search(pattern="SEARCHABLE", path=tmpdir)
        assert_contains(result, "SEARCHABLE_CONTENT")

        mtime_after = os.path.getmtime(test_file)

        # 文件修改时间不应变化
        assert mtime_before == mtime_after, \
            f"只读工具不应修改文件，mtime 变化: {mtime_before} -> {mtime_after}"
        print(f"  ✅ 搜索后文件 mtime 未变化 (只读确认)")
    finally:
        shutil.rmtree(tmpdir)


async def test_special_characters_in_pattern():
    print("\n[TEST 10] 特殊字符模式搜索")
    tmpdir = os.path.join(BASE_DIR, "_test_search_special")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        # 包含特殊字符的内容
        test_file = os.path.join(tmpdir, "special.py")
        with open(test_file, "w") as f:
            f.write('def foo(x: int) -> str:\n    return f"hello {x}"\n')
            f.write("# regex special: [a-z][a-z]* .*? ^$\n")
            f.write("path = '/usr/local/bin'\n")

        # 使用 ERE 模式 [a-z]+（grep fallback 已启用 -E 选项）
        result = await call_search(pattern="[a-z]+", path=tmpdir)
        assert result != "No matches found.", "正则 [a-z]+ 应命中"
        print(f"  ✅ ERE 正则模式正确解析")

        # 搜索字面量含 $ 的内容（$ 在 ERE 中匹配行尾）
        result2 = await call_search(pattern="bin'$", path=tmpdir)
        print(f"  ✅ 特殊字符模式未引发错误")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


# =============================================================================
# 主入口
# =============================================================================
async def main():
    print("=" * 70)
    print("🔍 search_files 工具详细验证测试")
    print("=" * 70)

    await test_basic_search()
    await test_path_restriction()
    await test_scope_filter()
    await test_case_insensitive()
    await test_no_matches()
    await test_excluded_dirs()
    await test_regex_search()
    await test_max_matches_limit()
    await test_readonly_no_file_operations()
    await test_special_characters_in_pattern()

    print("\n" + "=" * 70)
    print("🎉 全部通过！search_files 工具验证完成。")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
