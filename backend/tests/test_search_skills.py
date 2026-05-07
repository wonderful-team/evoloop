"""
🔍 search_skills 工具测试

覆盖场景：
1. Index Mode 浏览目录
2. Search Mode - 精确匹配（match + relevant）
3. Search Mode - 建议列表（relevant 但无 match）
4. Search Mode - 无匹配
5. Registry 注册与元数据
6. 参数默认值
7. 空查询行为
8. 特殊字符查询
9. 真实调用（可选，依赖 LLM）
"""

import sys
import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, ".")

from app.core.tools.registry import _ensure_scanned, REGISTRY
from app.core.learning.discovery import skill_discovery

_ensure_scanned()
search_skills_tool = REGISTRY.get_tool_map()["search_skills"]


def _extract_data(result):
    """从 ToolResult 中提取 JSON 数据字典。"""
    text = str(result)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def print_section(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def print_result(label, passed, detail=""):
    icon = "✅" if passed else "❌"
    extra = f" — {detail}" if detail else ""
    print(f"  {icon} {label}{extra}")


# ──────────────────────────────────────────────────────────
# Mock 数据构造
# ──────────────────────────────────────────────────────────

def make_mock_skill(skill_id, name, description, namespace="general", tools_used=None):
    """构造模拟的 LearnedSkill 对象。"""
    skill = MagicMock()
    skill.id = skill_id
    skill.name = name
    skill.description = description
    skill.namespace = namespace
    skill.instructions = f"# {name}\n\nMock instructions for {name}."
    skill.tools_used = tools_used or '[]'
    return skill


def make_mock_match(skill_id, skill_name, confidence=0.95):
    """构造模拟的 SkillMatch 对象。"""
    match = MagicMock()
    match.skill_id = skill_id
    match.skill_name = skill_name
    match.confidence = confidence
    return match


# ──────────────────────────────────────────────────────────
# 测试用例
# ──────────────────────────────────────────────────────────

async def test_index_mode():
    """TEST 1: Index Mode - 浏览 namespace 目录"""
    print_section("TEST 1: Index Mode 浏览目录")

    mock_index = [
        {"id": 1, "name": "android_click", "description": "Click on Android UI elements"},
        {"id": 2, "name": "android_scroll", "description": "Scroll on Android screen"},
        {"id": 3, "name": "android_screenshot", "description": "Capture Android screen"},
    ]

    with patch.object(skill_discovery, "get_namespace_index", new_callable=AsyncMock) as mock_index_fn:
        mock_index_fn.return_value = mock_index

        result = await search_skills_tool.ainvoke({
            "query": "",
            "namespace": "android",
            "index_mode": True,
        })
        data = _extract_data(result)

        passed = (
            data.get("result_type") == "index"
            and data.get("namespace") == "android"
            and len(data.get("skills", [])) == 3
            and data["skills"][0]["name"] == "android_click"
        )
        print_result("result_type 为 index", data.get("result_type") == "index")
        print_result("namespace 正确", data.get("namespace") == "android")
        print_result("返回 3 个技能", len(data.get("skills", [])) == 3)
        print_result("包含 instruction", "instruction" in data)
        print_result("TEST 1 整体", passed)
        return passed


async def test_search_mode_match():
    """TEST 2: Search Mode - 精确匹配"""
    print_section("TEST 2: Search Mode - 精确匹配")

    mock_skill = make_mock_skill(42, "click_save_button", "Click the save button in web UI", "web", '["browser_control"]')
    mock_match = make_mock_match(42, "click_save_button", 0.92)

    with patch.object(skill_discovery, "semantic_search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = (mock_match, [mock_skill], "Matched save button click pattern")

        result = await search_skills_tool.ainvoke({
            "query": "click save button",
            "namespace": "web",
            "index_mode": False,
        })
        data = _extract_data(result)

        passed = (
            data.get("result_type") == "match"
            and data.get("skill_name") == "click_save_button"
            and data.get("skill_id") == 42
            and data.get("confidence") == 0.92
            and "browser_control" in data.get("tools_required", [])
            and "markdown_sop" in data
            and "instruction" in data
        )
        print_result("result_type 为 match", data.get("result_type") == "match")
        print_result("skill_name 正确", data.get("skill_name") == "click_save_button")
        print_result("skill_id 正确", data.get("skill_id") == 42)
        print_result("confidence 正确", data.get("confidence") == 0.92)
        print_result("tools_required 包含 browser_control", "browser_control" in data.get("tools_required", []))
        print_result("包含 markdown_sop", "markdown_sop" in data)
        print_result("TEST 2 整体", passed)
        return passed


async def test_search_mode_suggestions():
    """TEST 3: Search Mode - 有建议但无精确匹配"""
    print_section("TEST 3: Search Mode - 建议列表")

    mock_skills = [
        make_mock_skill(1, "web_login", "Login to web app", "web"),
        make_mock_skill(2, "web_logout", "Logout from web app", "web"),
        make_mock_skill(3, "web_register", "Register new account", "web"),
    ]

    with patch.object(skill_discovery, "semantic_search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = (None, mock_skills, "No exact match found")

        result = await search_skills_tool.ainvoke({
            "query": "authenticate user",
            "namespace": "web",
        })
        data = _extract_data(result)

        passed = (
            data.get("result_type") == "suggestions"
            and len(data.get("suggestions", [])) == 3
            and data["suggestions"][0]["name"] == "web_login"
            and "instruction" in data
        )
        print_result("result_type 为 suggestions", data.get("result_type") == "suggestions")
        print_result("返回 3 个建议", len(data.get("suggestions", [])) == 3)
        print_result("建议包含 name/id/description", "name" in data["suggestions"][0] if data.get("suggestions") else False)
        print_result("TEST 3 整体", passed)
        return passed


async def test_search_mode_no_match():
    """TEST 4: Search Mode - 完全无匹配"""
    print_section("TEST 4: Search Mode - 无匹配")

    with patch.object(skill_discovery, "semantic_search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = (None, [], "No matching skills found")

        result = await search_skills_tool.ainvoke({
            "query": "fly to the moon",
        })
        data = _extract_data(result)

        passed = (
            data.get("result_type") == "no_match"
            and "fly to the moon" in data.get("instruction", "")
            and "Divergence Tip" in data.get("instruction", "")
        )
        print_result("result_type 为 no_match", data.get("result_type") == "no_match")
        print_result("instruction 包含查询词", "fly to the moon" in data.get("instruction", ""))
        print_result("instruction 包含 Divergence Tip", "Divergence Tip" in data.get("instruction", ""))
        print_result("TEST 4 整体", passed)
        return passed


async def test_registry_registration():
    """TEST 5: Registry 注册与元数据验证"""
    print_section("TEST 5: Registry 注册与元数据验证")

    tool = search_skills_tool
    meta = tool.metadata if hasattr(tool, "metadata") else {}

    checks = [
        ("Registry 中存在", tool is not None),
        ("名称正确", tool.name == "search_skills"),
        ("有 description", bool(tool.description)),
        ("非 pollable", meta.get("is_pollable") is False),
        ("非 state_mutating", meta.get("is_state_mutating") is False),
        ("name_map 包含中文", "zh" in meta.get("name_map", {})),
        ("handle_tool_error=True", getattr(tool, "handle_tool_error", False) is True),
    ]

    for label, ok in checks:
        print_result(label, ok)

    passed = all(ok for _, ok in checks)
    print_result("TEST 5 整体", passed)
    return passed


async def test_default_parameters():
    """TEST 6: 参数默认值"""
    print_section("TEST 6: 参数默认值")

    with patch.object(skill_discovery, "semantic_search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = (None, [], "test")

        # 只传 query，其他用默认值
        result = await search_skills_tool.ainvoke({"query": "test"})

        call_kwargs = mock_search.call_args.kwargs
        passed = (
            call_kwargs.get("query") == "test"
            and call_kwargs.get("namespace_context") is None
        )
        print_result("query 正确传递", call_kwargs.get("query") == "test")
        print_result("namespace_context 默认 None", call_kwargs.get("namespace_context") is None)
        print_result("TEST 6 整体", passed)
        return passed


async def test_empty_query():
    """TEST 7: 空查询行为（默认 query=""）"""
    print_section("TEST 7: 空查询行为")

    with patch.object(skill_discovery, "semantic_search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = (None, [], "empty query")

        # 不传任何参数，全部用默认值
        result = await search_skills_tool.ainvoke({})

        call_kwargs = mock_search.call_args.kwargs
        passed = call_kwargs.get("query") == ""
        print_result("空 query 被传递", call_kwargs.get("query") == "")
        print_result("返回结果不为空", bool(result))
        print_result("TEST 7 整体", passed)
        return passed


async def test_special_characters():
    """TEST 8: 特殊字符查询"""
    print_section("TEST 8: 特殊字符查询")

    special_queries = [
        ("HTML", "<script>alert(1)</script>"),
        ("SQL", "'; DROP TABLE skills; --"),
        ("Unicode", "搜索中文技能 🔍"),
        ("换行", "line1\nline2"),
        ("长查询", "A" * 1000),
    ]

    with patch.object(skill_discovery, "semantic_search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = (None, [], "test")

        all_passed = True
        for label, query in special_queries:
            result = await search_skills_tool.ainvoke({"query": query})
            ok = bool(result) and "Error:" not in str(result)
            if not ok:
                print(f"  ❌ [{label}] 失败")
                all_passed = False
            else:
                print(f"  ✅ [{label}] 通过")

        print_result("TEST 8 整体", all_passed)
        return all_passed


async def test_tools_used_json_parse_error():
    """TEST 9: tools_used JSON 解析失败容错"""
    print_section("TEST 9: tools_used JSON 解析容错")

    # tools_used 是非法 JSON
    mock_skill = make_mock_skill(1, "bad_json_skill", "Test", tools_used="not valid json")
    mock_match = make_mock_match(1, "bad_json_skill")

    with patch.object(skill_discovery, "semantic_search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = (mock_match, [mock_skill], "match")

        result = await search_skills_tool.ainvoke({"query": "test"})
        data = _extract_data(result)

        passed = (
            data.get("result_type") == "match"
            and data.get("tools_required") == []
        )
        print_result("result_type 为 match", data.get("result_type") == "match")
        print_result("tools_required 为空列表（容错）", data.get("tools_required") == [])
        print_result("未崩溃", "Error:" not in str(result))
        print_result("TEST 9 整体", passed)
        return passed


async def test_real_search():
    """TEST 10: 真实搜索（依赖 LLM 和数据库）"""
    print_section("TEST 10: 真实搜索（依赖 LLM + 数据库）")

    try:
        result = await search_skills_tool.ainvoke({
            "query": "click button",
            "namespace": "",
            "index_mode": False,
        })

        if not result or "Error" in str(result):
            print("  ⚠️ 真实搜索失败或返回错误，跳过")
            return True

        data = _extract_data(result)
        result_type = data.get("result_type", "unknown")
        print_result(f"返回类型: {result_type}", True)
        print_result("结果非空", bool(result))
        print_result("TEST 10 整体", True)
        return True

    except Exception as e:
        print(f"  ⚠️ 真实搜索异常: {e}，跳过")
        return True


# ──────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────

async def main():
    print("\n" + "=" * 70)
    print("🔍 search_skills 工具测试")
    print("=" * 70)

    tests = [
        ("Index Mode 浏览目录", test_index_mode),
        ("Search Mode - 精确匹配", test_search_mode_match),
        ("Search Mode - 建议列表", test_search_mode_suggestions),
        ("Search Mode - 无匹配", test_search_mode_no_match),
        ("Registry 注册与元数据", test_registry_registration),
        ("参数默认值", test_default_parameters),
        ("空查询行为", test_empty_query),
        ("特殊字符查询", test_special_characters),
        ("tools_used JSON 容错", test_tools_used_json_parse_error),
        ("真实搜索", test_real_search),
    ]

    results = []
    for name, test_fn in tests:
        try:
            ok = await test_fn()
            results.append((name, ok))
        except Exception as e:
            print(f"\n  ❌ 测试 '{name}' 抛异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    print("\n" + "=" * 70)
    print("📊 测试结果汇总")
    print("=" * 70)
    for name, passed in results:
        icon = "✅" if passed else "❌"
        print(f"  {icon} {name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\n  总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 全部通过！search_skills 测试完成。")
    else:
        print(f"\n⚠️ {total - passed} 个测试未通过")

    return all(r[1] for r in results)


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
