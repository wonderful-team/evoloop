"""
search_files 工具 — search_in_name 模式验证测试。

验证场景：
1. 按文件名搜索并返回原文
2. 文件名大小写不敏感搜索
3. scope 与 search_in_name 组合
4. 无匹配情况
5. 多文件命中限制（最多 5 个）
6. 长文件截断（最多 50 行）
7. 与 content 搜索模式对比
"""

import asyncio
import os
import sys
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from app.domain.tools.files.search_files import search_files_internal


async def call_search(**kwargs) -> str:
    return await search_files_internal(**kwargs)


def assert_contains(text: str, *substrings):
    for s in substrings:
        assert s in text, f"期望结果包含 '{s}'，实际:\n{text[:500]}"


# =============================================================================
# 测试场景
# =============================================================================
async def test_search_by_name_basic():
    print("\n[TEST 1] 按文件名搜索并返回原文")
    tmpdir = os.path.join(BASE_DIR, "_test_search_name_basic")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        # 创建几个文件
        with open(os.path.join(tmpdir, "user_service.py"), "w") as f:
            f.write("class UserService:\n    def get_user(self):\n        pass\n")
        with open(os.path.join(tmpdir, "order_service.py"), "w") as f:
            f.write("class OrderService:\n    def get_order(self):\n        pass\n")
        with open(os.path.join(tmpdir, "utils.py"), "w") as f:
            f.write("def helper():\n    pass\n")

        result = await call_search(pattern="user", path=tmpdir, search_in_name=True)
        assert_contains(result, "=== File:", "user_service.py", "class UserService")
        assert "order_service.py" not in result, "不应命中不含 user 的文件名"
        assert "utils.py" not in result
        print(f"  ✅ 命中 user_service.py，返回了原文内容")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_search_by_name_case_insensitive():
    print("\n[TEST 2] 文件名大小写不敏感搜索")
    tmpdir = os.path.join(BASE_DIR, "_test_search_name_ci")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "UserModel.py"), "w") as f:
            f.write("# UserModel\n")
        with open(os.path.join(tmpdir, "usermanager.py"), "w") as f:
            f.write("# UserManager\n")

        result = await call_search(pattern="USER", path=tmpdir, case_insensitive=True, search_in_name=True)
        assert_contains(result, "UserModel.py", "usermanager.py")
        print(f"  ✅ 大小写不敏感命中 2 个文件")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_search_by_name_with_scope():
    print("\n[TEST 3] search_in_name + scope 组合")
    tmpdir = os.path.join(BASE_DIR, "_test_search_name_scope")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "config.py"), "w") as f:
            f.write("DB_HOST = 'localhost'\n")
        with open(os.path.join(tmpdir, "config.json"), "w") as f:
            f.write('{"host": "localhost"}\n')
        with open(os.path.join(tmpdir, "app.py"), "w") as f:
            f.write("# app\n")

        # scope=*.py + search_in_name=config → 只命中 config.py
        result = await call_search(pattern="config", path=tmpdir, scope="*.py", search_in_name=True)
        assert_contains(result, "config.py", "DB_HOST")
        assert "config.json" not in result, "scope=*.py 应过滤掉 json 文件"
        print(f"  ✅ scope=*.py 正确过滤，只命中 config.py")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_search_by_name_no_matches():
    print("\n[TEST 4] 无匹配情况")
    tmpdir = os.path.join(BASE_DIR, "_test_search_name_empty")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "a.py"), "w") as f:
            f.write("# a\n")

        result = await call_search(pattern="NONEXISTENT", path=tmpdir, search_in_name=True)
        assert result == "No files found matching the name pattern.", f"实际: {repr(result)}"
        print(f"  ✅ 无匹配时正确返回提示")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_search_by_name_max_files_param():
    print("\n[TEST 5] 多文件命中限制（最多 5 个）")
    tmpdir = os.path.join(BASE_DIR, "_test_search_name_max")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        for i in range(8):
            with open(os.path.join(tmpdir, f"user_{i}.py"), "w") as f:
                f.write(f"# user {i}\n")

        result = await call_search(pattern="user", path=tmpdir, search_in_name=True)
        # 8 个文件 < 默认 max_files=20，不应出现限制提示
        assert "Showing first" not in result, "文件数未超限，不应出现限制提示"
        # 确认返回了全部 8 个文件的内容
        file_headers = [line for line in result.split('\n') if line.startswith('=== File:')]
        assert len(file_headers) == 8, f"应显示全部 8 个文件，实际显示 {len(file_headers)}"
        print(f"  ✅ 默认 max_files=20，8 个文件全部显示")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_search_by_name_max_files_limit():
    print("\n[TEST 5b] max_files 参数限制生效（设为 3）")
    tmpdir = os.path.join(BASE_DIR, "_test_search_name_max3")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        for i in range(8):
            with open(os.path.join(tmpdir, f"user_{i}.py"), "w") as f:
                f.write(f"# user {i}\n")

        result = await call_search(pattern="user", path=tmpdir, search_in_name=True, max_files=3)
        assert_contains(result, "Showing first 3 files", "5 more not displayed")
        file_headers = [line for line in result.split('\n') if line.startswith('=== File:')]
        assert len(file_headers) == 3, f"应只显示 3 个文件，实际显示 {len(file_headers)}"
        print(f"  ✅ max_files=3 正确限制，提示还有 5 个未显示")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_search_by_name_long_file_truncation():
    print("\n[TEST 6] 长文件截断（最多 50 行）")
    tmpdir = os.path.join(BASE_DIR, "_test_search_name_trunc")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "long_file.py"), "w") as f:
            for i in range(80):
                f.write(f"line_{i} = {i}\n")

        result = await call_search(pattern="long", path=tmpdir, search_in_name=True)
        assert_contains(result, "=== File:", "line_0", "line_49")
        assert_contains(result, "50 lines shown", "80 total")
        assert "line_60" not in result, "超过 50 行应被截断"
        print(f"  ✅ 正确截断为 50 行并提示文件继续")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


async def test_content_vs_name_mode():
    print("\n[TEST 7] content 模式 vs name 模式对比")
    tmpdir = os.path.join(BASE_DIR, "_test_search_name_vs_content")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "user.py"), "w") as f:
            f.write("class User:\n    pass\n")
        with open(os.path.join(tmpdir, "order.py"), "w") as f:
            f.write("from user import User\n")

        # content 模式: 搜索所有文件内容中的 "user"
        content_result = await call_search(pattern="user", path=tmpdir, search_in_name=False)
        # order.py 包含 "from user import User"
        # user.py 的内容是 "class User:"，也包含 User（但 search 默认区分大小写）
        assert_contains(content_result, "order.py")
        print(f"  ✅ content 模式命中 {len(content_result.splitlines())} 行")

        # name 模式: 只搜索文件名包含 "user" 的文件
        name_result = await call_search(pattern="user", path=tmpdir, search_in_name=True)
        assert_contains(name_result, "user.py", "class User:")
        assert "order.py" not in name_result, "name 模式不应命中 order.py"
        print(f"  ✅ name 模式只命中 user.py，返回了原文")
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)


# =============================================================================
# 主入口
# =============================================================================
async def main():
    print("=" * 70)
    print("🔍 search_files — search_in_name 模式验证")
    print("=" * 70)

    await test_search_by_name_basic()
    await test_search_by_name_case_insensitive()
    await test_search_by_name_with_scope()
    await test_search_by_name_no_matches()
    await test_search_by_name_max_files_param()
    await test_search_by_name_max_files_limit()
    await test_search_by_name_long_file_truncation()
    await test_content_vs_name_mode()

    print("\n" + "=" * 70)
    print("🎉 全部通过！search_in_name 模式验证完成。")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
