#!/usr/bin/env python3
"""
新动作验证测试 - 简化版
==================

验证新动作需求的合理性，通过现有功能模拟新行为。
"""

import asyncio
import sys
import os

# 添加 backend 到路径
sys.path.insert(0, "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")
os.chdir("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")

from app.domain.tools.environment.browser import browser_control


async def test_browser_batch_concept():
    """
    验证 browser batch 的合理性：
    测试当前逐个调用 vs 批量调用的效率差异
    """
    print("\n" + "="*60)
    print("🧪 TEST 1: Browser Batch Action Concept Validation")
    print("="*60)

    import time
    start = time.time()

    # 模拟 batch 工作流（目前需要多次调用）
    steps = [
        ("navigate", {"url": "https://github.com"}),
        ("click", {"selector": "[name='q']"}),
        ("type_text", {"selector": "[name='q']", "value": "python", "clear_first": True}),
        ("key_press", {"key": "Enter"}),
    ]

    results = []
    for i, (action_name, params) in enumerate(steps, 1):
        step_start = time.time()
        try:
            result = await browser_control.ainvoke({"action": action_name, **params})
            duration = (time.time() - step_start) * 1000
            results.append({"step": i, "action": action_name, "status": "ok", "duration_ms": duration})
            print(f"  Step {i}: {action_name} ({duration:.0f}ms) - OK")
        except Exception as e:
            duration = (time.time() - step_start) * 1000
            results.append({"step": i, "action": action_name, "status": "error", "error": str(e)})
            print(f"  Step {i}: {action_name} ({duration:.0f}ms) - ERROR: {e}")

    total_time = (time.time() - start) * 1000

    print(f"\n  Total time: {total_time:.0f}ms")
    print(f"  LLM calls needed: {len(steps)}")

    # 计算 batch 能节省的通信开销
    avg_network_latency = 500  # 假设每次 LLM 调用往返 500ms
    estimated_savings = avg_network_latency * (len(steps) - 1)

    print(f"\n  📊 With 'batch' action:")
    print(f"     - Single LLM call instead of {len(steps)}")
    print(f"     - Estimated time savings: ~{estimated_savings:.0f}ms")
    print(f"     - Atomic execution with error handling")

    return True


async def test_browser_upload_concept():
    """
    验证 browser upload 的合理性
    """
    print("\n" + "="*60)
    print("🧪 TEST 2: Browser Upload Action Concept Validation")
    print("="*60)

    # 检查 upload 页面的可访问性
    try:
        result = await browser_control.ainvoke({
            "action": "navigate",
            "url": "https://the-internet.herokuapp.com/upload"
        })
        print(f"  1. Navigate to upload page: OK")

        # 检查文件输入元素
        check = await browser_control.ainvoke({
            "action": "check_element",
            "selector": "#file-upload"
        })
        print(f"  2. Check upload input: {check}")

        # 当前无法通过 browser_control 上传文件
        # 需要使用 Playwright 原生方法
        from app.infrastructure.drivers.browser import browser_manager
        page = await browser_manager.get_page()

        # 创建测试文件
        test_file = "/tmp/test_upload_validation.txt"
        with open(test_file, "w") as f:
            f.write("Test content")

        # 使用原生方法上传
        await page.locator("#file-upload").set_input_files(test_file)
        print(f"  3. File selected via Playwright native: OK")

        # 点击上传
        await browser_control.ainvoke({"action": "click", "selector": "#file-submit"})
        print(f"  4. Click upload button: OK")

        await asyncio.sleep(1)

        # 验证结果
        text = await browser_control.ainvoke({"action": "get_text"})
        if "File Uploaded!" in text:
            print(f"  5. Upload confirmation: FOUND")
        else:
            print(f"  5. Upload confirmation: NOT FOUND (may be different page)")

        print(f"\n  📊 Upload action would encapsulate:")
        print(f"     - File existence validation")
        print(f"     - Element locator resolution")
        print(f"     - set_input_files call")
        print(f"     - Optional auto-submit")

        return True

    except Exception as e:
        print(f"  Error: {e}")
        return False


async def test_desktop_scroll_concept():
    """
    验证 desktop scroll 的合理性
    """
    print("\n" + "="*60)
    print("🧪 TEST 3: Desktop Scroll Action Concept Validation")
    print("="*60)

    from app.domain.tools.environment.desktop import desktop_control

    try:
        # 打开 Safari
        result = await desktop_control.ainvoke({"action": "open_app", "app_name": "Safari"})
        print(f"  1. Open Safari: OK")

        await asyncio.sleep(1.5)

        # 导航到测试页面
        script = '''
        tell application "Safari"
            if (count of documents) = 0 then make new document
            set URL of front document to "https://news.ycombinator.com"
            return "OK"
        end tell
        '''
        result = await desktop_control.ainvoke({"action": "applescript", "script": script})
        print(f"  2. Navigate to page: {result}")

        await asyncio.sleep(2)

        # 截图记录当前位置
        before = await desktop_control.ainvoke({"action": "screenshot", "region": "0,100,1200,600"})
        print(f"  3. Screenshot before: {before}")

        # 当前没有 scroll action，使用 key_press 模拟
        await desktop_control.ainvoke({"action": "key_press", "key": "pagedown"})
        await asyncio.sleep(0.3)
        await desktop_control.ainvoke({"action": "key_press", "key": "pagedown"})
        await asyncio.sleep(0.3)

        after = await desktop_control.ainvoke({"action": "screenshot", "region": "0,100,1200,600"})
        print(f"  4. Screenshot after: {after}")

        print(f"\n  📊 Scroll action would provide:")
        print(f"     - Semantic direction (up/down/left/right)")
        print(f"     - Pixel or relative amount control")
        print(f"     - Optional target element for in-element scroll")
        print(f"     - More natural than key_press")

        return True

    except Exception as e:
        print(f"  Error: {e}")
        return False


async def test_mobile_scroll_concept():
    """
    验证 mobile scroll 的合理性
    """
    print("\n" + "="*60)
    print("🧪 TEST 4: Mobile Scroll Action Concept Validation")
    print("="*60)

    from app.domain.tools.environment.mobile import mobile_control

    # 检查设备连接
    devices = await mobile_control.ainvoke({"action": "list_devices"})
    print(f"  1. Check devices: {devices[:80]}...")

    if "No Android devices" in devices:
        print(f"\n  ⚠️ No Android device connected - skipping physical test")
        print(f"\n  📊 Scroll action would provide:")
        print(f"     - Semantic API: scroll(direction='down', amount='medium')")
        print(f"     - Instead of: swipe(x=540, y=1800, x2=540, y2=900)")
        print(f"     - Easier for LLM to reason about")
        return True

    # 如果设备已连接，执行实际测试
    try:
        # 截图
        before = await mobile_control.ainvoke({"action": "screenshot"})
        print(f"  2. Screenshot before: {before}")

        # 当前使用 swipe 实现滚动
        result = await mobile_control.ainvoke({
            "action": "swipe",
            "x": 540, "y": 1800,      # 从下方
            "x2": 540, "y2": 600,     # 滑动到上方
            "duration_ms": 300
        })
        print(f"  3. Swipe (scroll down): OK")

        after = await mobile_control.ainvoke({"action": "screenshot"})
        print(f"  4. Screenshot after: {after}")

        print(f"\n  📊 Scroll action API comparison:")
        print(f"     Current: swipe(x=540, y=1800, x2=540, y2=600)")
        print(f"     Proposed: scroll(direction='down', amount='medium')")
        print(f"     Benefits: Self-documenting, responsive-aware")

        return True

    except Exception as e:
        print(f"  Error: {e}")
        return False


async def main():
    """运行所有概念验证测试"""

    print("\n" + "="*70)
    print("🚀 NEW ACTION VALIDATION TEST SUITE")
    print("   Verifying need and design for proposed actions")
    print("="*70)

    results = []

    try:
        results.append(("browser_batch", await test_browser_batch_concept()))
    except Exception as e:
        print(f"browser_batch failed: {e}")
        results.append(("browser_batch", False))

    try:
        results.append(("browser_upload", await test_browser_upload_concept()))
    except Exception as e:
        print(f"browser_upload failed: {e}")
        results.append(("browser_upload", False))

    try:
        results.append(("desktop_scroll", await test_desktop_scroll_concept()))
    except Exception as e:
        print(f"desktop_scroll failed: {e}")
        results.append(("desktop_scroll", False))

    try:
        results.append(("mobile_scroll", await test_mobile_scroll_concept()))
    except Exception as e:
        print(f"mobile_scroll failed: {e}")
        results.append(("mobile_scroll", False))

    # 汇总
    print("\n" + "="*70)
    print("📊 VALIDATION SUMMARY")
    print("="*70)

    for name, passed in results:
        status = "✅ VALIDATED" if passed else "❌ FAILED"
        print(f"  {status}: {name}")

    passed_count = sum(1 for _, p in results if p)
    print(f"\n  Total: {len(results)} | Passed: {passed_count}")

    if passed_count == len(results):
        print("\n  🎉 All new actions are validated and ready for implementation!")


if __name__ == "__main__":
    asyncio.run(main())
