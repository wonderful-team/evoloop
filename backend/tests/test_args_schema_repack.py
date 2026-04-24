"""
🔧 工具 flat 参数签名回归测试

验证 browser_control / desktop_control / mobile_control / verify_ui_state / quick_check_screen
改回 flat 参数形式后，LangChain StructuredTool 能正常调用。

修复的 Bug：
  browser_control() got an unexpected keyword argument 'action'
  （之前使用 args_schema + 单一模型参数导致 LangChain flat dict 传入失败）
"""

import sys
import asyncio
from unittest.mock import patch, AsyncMock

sys.path.insert(0, ".")

from app.core.tools.registry import _ensure_scanned, REGISTRY

_ensure_scanned()


def print_section(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def print_result(label, passed, detail=""):
    icon = "✅" if passed else "❌"
    extra = f" — {detail}" if detail else ""
    print(f"  {icon} {label}{extra}")


# ──────────────────────────────────────────────────────────
# 1. browser_control flat 参数调用
# ──────────────────────────────────────────────────────────

async def test_browser_control_flat():
    """TEST 1: browser_control 接受 flat dict 参数直接调用"""
    print_section("TEST 1: browser_control flat 参数调用")

    tool = REGISTRY.get_tool_map()["browser_control"]

    with patch("app.domain.tools.environment.browser.BrowserController.execute", new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = "Navigated to https://www.pearsonpte.com/"

        # 传入 flat dict（LangChain StructuredTool 的标准调用方式）
        result = await tool.ainvoke({
            "action": "navigate",
            "url": "https://www.pearsonpte.com/"
        })

        passed = mock_execute.called
        print_result("BrowserController.execute 被调用", mock_execute.called)

        if mock_execute.called:
            call_kwargs = mock_execute.call_args.kwargs
            print_result("action 正确", call_kwargs.get("action") == "navigate")
            print_result("url 正确", call_kwargs.get("url") == "https://www.pearsonpte.com/")
            passed = passed and call_kwargs.get("action") == "navigate" and call_kwargs.get("url") == "https://www.pearsonpte.com/"

        print_result("未报 'unexpected keyword argument'", "Error:" not in result)
        passed = passed and "Error:" not in result

        print_result("TEST 1 整体", passed)
        return passed


# ──────────────────────────────────────────────────────────
# 2. desktop_control flat 参数调用
# ──────────────────────────────────────────────────────────

async def test_desktop_control_flat():
    """TEST 2: desktop_control flat 参数调用"""
    print_section("TEST 2: desktop_control flat 参数调用")

    tool = REGISTRY.get_tool_map().get("desktop_control")
    if not tool:
        print("  ⚠️ desktop_control 未注册，跳过")
        return True

    with patch("app.domain.tools.environment.desktop.DesktopController.execute", new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = "Clicked at (100, 200)"

        result = await tool.ainvoke({
            "action": "click",
            "x": 100,
            "y": 200,
        })

        passed = mock_execute.called and "Error:" not in result
        print_result("DesktopController.execute 被调用", mock_execute.called)
        print_result("未报参数错误", "Error:" not in result)
        if mock_execute.called:
            call_kwargs = mock_execute.call_args.kwargs
            print_result("x 正确", call_kwargs.get("x") == 100)
            print_result("y 正确", call_kwargs.get("y") == 200)
            passed = passed and call_kwargs.get("x") == 100 and call_kwargs.get("y") == 200
        print_result("TEST 2 整体", passed)
        return passed


# ──────────────────────────────────────────────────────────
# 3. mobile_control flat 参数调用
# ──────────────────────────────────────────────────────────

async def test_mobile_control_flat():
    """TEST 3: mobile_control flat 参数调用"""
    print_section("TEST 3: mobile_control flat 参数调用")

    tool = REGISTRY.get_tool_map().get("mobile_control")
    if not tool:
        print("  ⚠️ mobile_control 未注册，跳过")
        return True

    with patch("app.domain.tools.environment.mobile.MobileController.execute", new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = "Tapped screen"

        result = await tool.ainvoke({
            "action": "tap",
            "x": 100,
            "y": 200,
        })

        passed = mock_execute.called and "Error:" not in result
        print_result("MobileController.execute 被调用", mock_execute.called)
        print_result("未报参数错误", "Error:" not in result)
        print_result("TEST 3 整体", passed)
        return passed


# ──────────────────────────────────────────────────────────
# 4. verify_ui_state flat 参数调用
# ──────────────────────────────────────────────────────────

async def test_verify_ui_state_flat():
    """TEST 4: verify_ui_state flat 参数调用"""
    print_section("TEST 4: verify_ui_state flat 参数调用")

    tool = REGISTRY.get_tool_map().get("verify_ui_state")
    if not tool:
        print("  ⚠️ verify_ui_state 未注册，跳过")
        return True

    with patch("app.domain.tools.environment.desktop.DesktopController.verify_ui_state", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = "UI element found"

        result = await tool.ainvoke({
            "expected_element": "Search",
            "expected_role": "AXButton",
        })

        passed = mock_verify.called and "Error:" not in result
        print_result("verify_ui_state 被调用", mock_verify.called)
        print_result("未报参数错误", "Error:" not in result)
        print_result("TEST 4 整体", passed)
        return passed


# ──────────────────────────────────────────────────────────
# 5. quick_check_screen flat 参数调用
# ──────────────────────────────────────────────────────────

async def test_quick_check_screen_flat():
    """TEST 5: quick_check_screen flat 参数调用"""
    print_section("TEST 5: quick_check_screen flat 参数调用")

    tool = REGISTRY.get_tool_map().get("quick_check_screen")
    if not tool:
        print("  ⚠️ quick_check_screen 未注册，跳过")
        return True

    with patch("app.domain.tools.environment.desktop.DesktopController.quick_check_screen", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = "Screen loaded"

        result = await tool.ainvoke({
            "check_type": "has_text",
            "target": "Loading",
        })

        passed = mock_check.called and "Error:" not in result
        print_result("quick_check_screen 被调用", mock_check.called)
        print_result("未报参数错误", "Error:" not in result)
        print_result("TEST 5 整体", passed)
        return passed


# ──────────────────────────────────────────────────────────
# 6. 重复调用场景（日志中的 REPETITION DETECTED）
# ──────────────────────────────────────────────────────────

async def test_repeated_calls():
    """TEST 6: 重复调用场景"""
    print_section("TEST 6: 重复调用场景")

    tool = REGISTRY.get_tool_map()["browser_control"]

    with patch("app.domain.tools.environment.browser.BrowserController.execute", new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = "Navigated"

        result1 = await tool.ainvoke({"action": "navigate", "url": "https://a.com"})
        result2 = await tool.ainvoke({"action": "navigate", "url": "https://a.com"})
        result3 = await tool.ainvoke({"action": "click", "selector": "#btn"})

        passed = (
            mock_execute.call_count == 3
            and "Error:" not in result1
            and "Error:" not in result2
            and "Error:" not in result3
        )
        print_result("3 次调用全部成功", mock_execute.call_count == 3)
        print_result("无参数错误", "Error:" not in result1 + result2 + result3)
        print_result("TEST 6 整体", passed)
        return passed


# ──────────────────────────────────────────────────────────
# 7. 无 args_schema 工具不受影响
# ──────────────────────────────────────────────────────────

async def test_no_args_schema_unaffected():
    """TEST 7: 不使用 args_schema 的工具（如 search_web）不受影响"""
    print_section("TEST 7: 无 args_schema 工具不受影响")

    tool = REGISTRY.get_tool_map()["search_web"]

    with patch("app.domain.tools.research._search_duckduckgo", new_callable=AsyncMock) as mock_ddg:
        mock_ddg.return_value = ["Title: Test\nURL: https://test.com\nDescription: test\n"]

        result = await tool.ainvoke({"query": "test"})

        passed = mock_ddg.called and "Web Search Results" in result
        print_result("search_web 正常工作", passed)
        print_result("TEST 7 整体", passed)
        return passed


# ──────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────

async def main():
    print("\n" + "=" * 70)
    print("🔧 工具 flat 参数签名回归测试")
    print("=" * 70)

    tests = [
        ("browser_control flat 调用", test_browser_control_flat),
        ("desktop_control flat 调用", test_desktop_control_flat),
        ("mobile_control flat 调用", test_mobile_control_flat),
        ("verify_ui_state flat 调用", test_verify_ui_state_flat),
        ("quick_check_screen flat 调用", test_quick_check_screen_flat),
        ("重复调用场景", test_repeated_calls),
        ("无 args_schema 工具不受影响", test_no_args_schema_unaffected),
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
        print("\n🎉 全部通过！flat 参数签名回归测试完成。")
    else:
        print(f"\n⚠️ {total - passed} 个测试未通过")

    return all(r[1] for r in results)


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
