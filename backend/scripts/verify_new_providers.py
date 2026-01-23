#!/usr/bin/env python3
"""
验证新增语言 Provider 的测试脚本

测试内容：
1. Provider 注册验证
2. Parser 加载验证
3. 基本查询功能验证
"""

import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


def test_provider_registry():
    """测试 Provider 注册"""
    from app.domain.codebase.indexing.extractors.provider_registry import (
        semantic_provider_registry,
    )

    print("=" * 70)
    print("测试 1: Provider 注册验证")
    print("=" * 70)

    expected_providers = [
        "python",
        "typescript",
        "javascript",
        "java",
        "go",
        "csharp",
        "php",
        "ruby",
        "rust",
        "kotlin",
        "swift",
        "sql",
        "vue",
    ]

    all_providers = semantic_provider_registry.get_all()

    print(f"\n已注册的 Provider 数量: {len(all_providers)}")
    print(f"预期 Provider 数量: {len(expected_providers)}")

    missing = []
    for lang in expected_providers:
        provider = semantic_provider_registry.get(lang)
        if provider:
            print(f"  ✓ {lang:12} -> {provider.__class__.__name__}")
        else:
            print(f"  ✗ {lang:12} -> 未找到")
            missing.append(lang)

    if missing:
        print(f"\n❌ 缺少 Provider: {', '.join(missing)}")
        return False
    else:
        print(f"\n✅ 所有 {len(expected_providers)} 个 Provider 注册成功")
        return True


def test_parser_loaders():
    """测试 Parser Loader"""
    from app.domain.codebase.indexing.parsers import parser_registry

    print("\n" + "=" * 70)
    print("测试 2: Parser Loader 验证")
    print("=" * 70)

    test_cases = [
        ("py", "python"),
        ("php", "php"),
        ("rb", "ruby"),
        ("rs", "rust"),
        ("kt", "kotlin"),
        ("swift", "swift"),
        ("sql", "sql"),
        ("vue", "vue"),
        ("ts", "typescript"),
        ("js", "javascript"),
    ]

    success_count = 0
    failed = []

    for ext, expected_lang in test_cases:
        lang = parser_registry.get_language_key(ext)
        if lang == expected_lang:
            # Try to get parser (this will trigger lazy loading)
            try:
                result = parser_registry.get_parser(ext)
                if result:
                    parser, language = result
                    print(f"  ✓ .{ext:6} -> {expected_lang:12} (Parser 加载成功)")
                    success_count += 1
                else:
                    print(
                        f"  ⚠ .{ext:6} -> {expected_lang:12} (映射正确但 Parser 未安装)"
                    )
                    failed.append((ext, "Parser 未安装"))
            except Exception as e:
                print(f"  ✗ .{ext:6} -> {expected_lang:12} (加载失败: {e})")
                failed.append((ext, str(e)))
        else:
            print(f"  ✗ .{ext:6} -> 预期 {expected_lang}, 实际 {lang}")
            failed.append((ext, "映射错误"))

    print(f"\n成功: {success_count}/{len(test_cases)}")
    if failed:
        print(f"失败: {len(failed)} 个")
        for ext, reason in failed:
            print(f"  - .{ext}: {reason}")
        return False
    else:
        print("✅ 所有 Parser 加载成功")
        return True


def test_semantic_language_map():
    """测试 SEMANTIC_LANGUAGE_MAP"""
    from app.constants import SEMANTIC_LANGUAGE_MAP, SEMANTIC_EXTENSIONS

    print("\n" + "=" * 70)
    print("测试 3: SEMANTIC_LANGUAGE_MAP 验证")
    print("=" * 70)

    expected_languages = {
        "python",
        "typescript",
        "javascript",
        "java",
        "go",
        "csharp",
        "php",
        "ruby",
        "rust",
        "kotlin",
        "swift",
        "sql",
        "vue",
    }

    print(f"\n语言映射:")
    for lang, exts in sorted(SEMANTIC_LANGUAGE_MAP.items()):
        print(f"  {lang:12} -> {', '.join(exts)}")

    missing = expected_languages - set(SEMANTIC_LANGUAGE_MAP.keys())
    if missing:
        print(f"\n❌ 缺少语言: {', '.join(missing)}")
        return False

    print(f"\n✅ 所有 {len(expected_languages)} 个语言已配置")
    print(f"✅ 支持的文件扩展名总数: {len(SEMANTIC_EXTENSIONS)}")
    return True


def test_provider_queries():
    """测试 Provider 查询方法"""
    from app.domain.codebase.indexing.extractors.provider_registry import (
        semantic_provider_registry,
    )

    print("\n" + "=" * 70)
    print("测试 4: Provider 查询方法验证")
    print("=" * 70)

    test_providers = ["php", "ruby", "rust", "kotlin", "swift", "sql", "vue"]

    for lang in test_providers:
        provider = semantic_provider_registry.get(lang)
        if not provider:
            print(f"  ✗ {lang}: Provider 未找到")
            continue

        # Test get_language_name
        lang_name = provider.get_language_name()
        print(f"\n  {lang}:")
        print(f"    - get_language_name(): {lang_name}")

        # Test get_structure_query
        structure_query = provider.get_structure_query()
        if structure_query:
            print(f"    - get_structure_query(): ✓ ({len(structure_query)} chars)")
        else:
            print(f"    - get_structure_query(): (空)")

        # Test get_imports_query
        imports_query = provider.get_imports_query()
        if imports_query:
            print(f"    - get_imports_query(): ✓ ({len(imports_query)} chars)")
        else:
            print(f"    - get_imports_query(): (空)")

        # Test get_api_query
        api_query = provider.get_api_query()
        if api_query:
            print(f"    - get_api_query(): ✓ ({len(api_query)} chars)")
        else:
            print(f"    - get_api_query(): (空)")

    print(f"\n✅ Provider 查询方法测试完成")
    return True


def main():
    """运行所有测试"""
    print("🧪 开始验证新增语言 Provider\n")

    results = {
        "Provider 注册": test_provider_registry(),
        "Parser Loader": test_parser_loaders(),
        "SEMANTIC_LANGUAGE_MAP": test_semantic_language_map(),
        "Provider 查询方法": test_provider_queries(),
    }

    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)

    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{test_name:25} {status}")

    all_passed = all(results.values())
    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️  部分测试未通过，请检查依赖包是否已安装")
        print("\n安装缺失的 Tree-sitter 包:")
        print("  uv add tree-sitter-kotlin tree-sitter-swift tree-sitter-sql tree-sitter-html")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
