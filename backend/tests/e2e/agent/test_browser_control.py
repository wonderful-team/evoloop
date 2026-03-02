"""
Smoke test for browser_control tool.
Tests: navigate, get_text, get_url, screenshot (OCR), run_js, get_links, close.

Run with:
    cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
    python3 tests/test_browser_control.py
"""
import asyncio
import logging
import os

logging.basicConfig(level=logging.WARNING)


async def main():
    from app.domain.tools.environment.browser import browser_control

    sep = "─" * 60
    errors = []

    def check(label: str, result: str, expected_substr: str | None = None, expect_no_error: bool = True):
        ok = True
        if expect_no_error and result.startswith("Error"):
            ok = False
            errors.append(f"FAIL [{label}]: {result[:120]}")
        elif expected_substr and expected_substr.lower() not in result.lower():
            ok = False
            errors.append(f"FAIL [{label}]: expected '{expected_substr}' in result, got: {result[:120]}")
        icon = "✅" if ok else "❌"
        print(f"{icon} [{label}]\n   {result[:120]}")

    print(f"\n{sep}\n🧪 browser_control Smoke Test\n{sep}")

    # 1. Navigate
    r = await browser_control.ainvoke({"action": "navigate", "url": "https://example.com"})
    check("navigate", r, "example.com")

    # 2. get_url
    r = await browser_control.ainvoke({"action": "get_url"})
    check("get_url", r, "example.com")

    # 3. get_text
    r = await browser_control.ainvoke({"action": "get_text"})
    check("get_text", r, "Example Domain")

    # 4. run_js — page title
    r = await browser_control.ainvoke({"action": "run_js", "script": "document.title"})
    check("run_js (title)", r, "Example")

    # 5. get_attribute — textContent is a DOM property, falls back to JS eval
    r = await browser_control.ainvoke({"action": "get_attribute", "selector": "h1", "attribute": "textContent"})
    check("get_attribute (textContent)", r, "Example Domain")

    # 6. find_element
    r = await browser_control.ainvoke({"action": "find_element", "selector": "a[href]"})
    check("find_element", r, "found")

    # 7. get_links
    r = await browser_control.ainvoke({"action": "get_links"})
    check("get_links", r, "iana.org")

    # 8. screenshot (OCR should fire)
    r = await browser_control.ainvoke({"action": "screenshot"})
    check("screenshot", r, "Screenshot saved to")
    # verify file was created
    if "Screenshot saved to:" in r:
        path = r.split("Screenshot saved to:")[1].split("\n")[0].strip()
        assert os.path.exists(path), f"Screenshot file missing: {path}"
        os.remove(path)
        print("   📸 Screenshot file verified and cleaned up.")

    # 9. local_storage set/get
    r = await browser_control.ainvoke({"action": "local_storage", "storage_action": "set", "storage_key": "evo_test", "value": "42"})
    check("local_storage set", r)
    r = await browser_control.ainvoke({"action": "local_storage", "storage_action": "get", "storage_key": "evo_test"})
    check("local_storage get", r, "42")

    # 10. check_element
    r = await browser_control.ainvoke({"action": "check_element", "selector": "h1"})
    check("check_element", r, "visible=True")

    # 11. scroll
    r = await browser_control.ainvoke({"action": "scroll", "direction": "down", "amount": 100})
    check("scroll", r)

    # 12. key_press
    r = await browser_control.ainvoke({"action": "key_press", "key": "Tab"})
    check("key_press", r)

    # 13. close
    r = await browser_control.ainvoke({"action": "close"})
    check("close", r, "closed")

    print(f"\n{sep}")
    if errors:
        print(f"❌ {len(errors)} test(s) failed:")
        for e in errors:
            print(f"   {e}")
    else:
        print("✅ All smoke tests passed!")
    print(sep)


if __name__ == "__main__":
    asyncio.run(main())
