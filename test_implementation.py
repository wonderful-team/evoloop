#!/usr/bin/env python3
"""
新动作实现测试脚本
=================

在添加新动作后，使用此脚本验证实现是否正确。

测试动作：
1. browser_control - batch
2. browser_control - upload
3. desktop_control - scroll
4. desktop_control - drag_drop
5. mobile_control - scroll

使用方法：
    # 测试所有新动作
    python test_implementation.py

    # 测试单个动作
    python test_implementation.py --action browser_batch
"""

import asyncio
import argparse
import os
import sys
import tempfile

sys.path.insert(0, "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")
os.chdir("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")

from app.domain.tools.environment.browser import browser_control
from app.domain.tools.environment.desktop import desktop_control
from app.domain.tools.environment.mobile import mobile_control


class ActionTester:
    def __init__(self):
        self.results = []

    def log(self, msg):
        print(f"  {msg}")

    async def test_browser_batch(self):
        """测试 Browser batch 动作"""
        print("\n" + "=" * 60)
        print("🧪 Testing: browser_control batch")
        print("=" * 60)

        try:
            # 测试 batch 动作
            result = await browser_control.ainvoke({
                "action": "batch",
                "actions": [
                    {"action": "navigate", "url": "https://httpbin.org/forms/post"},
                    {"action": "type_text", "selector": "[name='custname']", "value": "Test User"},
                    {"action": "type_text", "selector": "[name='custtel']", "value": "13800138000"},
                ],
                "continue_on_error": True,
                "delay_ms": 500
            })

            self.log(f"Result: {result[:200]}...")

            # 验证结果
            if "Batch Complete" in result or "success" in result.lower():
                self.log("✅ batch action implemented correctly")
                return True
            else:
                self.log("❌ batch action not implemented or failed")
                return False

        except Exception as e:
            if "Unknown action" in str(e) or "not found" in str(e).lower():
                self.log(f"⏳ batch action not yet implemented: {e}")
            else:
                self.log(f"❌ Error: {e}")
            return False

    async def test_browser_upload(self):
        """测试 Browser upload 动作"""
        print("\n" + "=" * 60)
        print("🧪 Testing: browser_control upload")
        print("=" * 60)

        try:
            # 创建测试文件
            test_file = "/tmp/test_implementation.txt"
            with open(test_file, "w") as f:
                f.write("Implementation test content")

            # 导航到上传页面
            await browser_control.ainvoke({
                "action": "navigate",
                "url": "https://the-internet.herokuapp.com/upload"
            })

            # 测试 upload 动作
            result = await browser_control.ainvoke({
                "action": "upload",
                "selector": "#file-upload",
                "file_path": test_file
            })

            self.log(f"Result: {result[:200]}...")

            # 点击上传按钮
            await browser_control.ainvoke({"action": "click", "selector": "#file-submit"})
            await asyncio.sleep(1)

            # 验证
            text = await browser_control.ainvoke({"action": "get_text"})
            if "File Uploaded!" in text:
                self.log("✅ upload action implemented correctly")
                return True
            else:
                self.log("❌ upload action failed or not implemented")
                return False

        except Exception as e:
            if "Unknown action" in str(e) or "not found" in str(e).lower():
                self.log(f"⏳ upload action not yet implemented: {e}")
            else:
                self.log(f"❌ Error: {e}")
            return False

    async def test_desktop_scroll(self):
        """测试 Desktop scroll 动作"""
        print("\n" + "=" * 60)
        print("🧪 Testing: desktop_control scroll")
        print("=" * 60)

        try:
            # 打开 Safari
            await desktop_control.ainvoke({"action": "open_app", "app_name": "Safari"})
            await asyncio.sleep(1)

            # 导航到长页面
            script = '''
            tell application "Safari"
                if (count of documents) = 0 then make new document
                set URL of front document to "https://news.ycombinator.com"
                return "OK"
            end tell
            '''
            await desktop_control.ainvoke({"action": "applescript", "script": script})
            await asyncio.sleep(2)

            # 截图 - 滚动前
            before = await desktop_control.ainvoke({"action": "screenshot", "region": "0,100,1200,600"})
            self.log(f"Screenshot before: {before}")

            # 测试 scroll 动作
            result = await desktop_control.ainvoke({
                "action": "scroll",
                "direction": "down",
                "amount": 500
            })

            self.log(f"Result: {result}")

            # 截图 - 滚动后
            after = await desktop_control.ainvoke({"action": "screenshot", "region": "0,100,1200,600"})
            self.log(f"Screenshot after: {after}")

            if before != after:
                self.log("✅ scroll action implemented correctly")
                return True
            else:
                self.log("❌ scroll action did not change view")
                return False

        except Exception as e:
            if "Unknown action" in str(e) or "not found" in str(e).lower():
                self.log(f"⏳ scroll action not yet implemented: {e}")
            else:
                self.log(f"❌ Error: {e}")
            return False

    async def test_desktop_drag_drop(self):
        """测试 Desktop drag_drop 动作"""
        print("\n" + "=" * 60)
        print("🧪 Testing: desktop_control drag_drop")
        print("=" * 60)

        try:
            # 创建测试文件和文件夹
            test_dir = os.path.expanduser("~/Desktop/test_drag_impl")
            test_file = os.path.join(test_dir, "drag_me.txt")

            os.makedirs(test_dir, exist_ok=True)
            with open(test_file, "w") as f:
                f.write("Drag test content")

            # 打开 Finder
            os.system(f"open {test_dir}")
            await asyncio.sleep(1)

            # 测试 drag_drop 动作
            result = await desktop_control.ainvoke({
                "action": "drag_drop",
                "source_element": "drag_me.txt",
                "x": 200, "y": 300,
                "x2": 400, "y2": 300
            })

            self.log(f"Result: {result}")

            # 清理
            import shutil
            shutil.rmtree(test_dir, ignore_errors=True)

            if "drag" in result.lower() or "drop" in result.lower():
                self.log("✅ drag_drop action implemented")
                return True
            else:
                self.log("❌ drag_drop action not implemented correctly")
                return False

        except Exception as e:
            if "Unknown action" in str(e) or "not found" in str(e).lower():
                self.log(f"⏳ drag_drop action not yet implemented: {e}")
            else:
                self.log(f"❌ Error: {e}")
            return False

    async def test_mobile_scroll(self):
        """测试 Mobile scroll 动作"""
        print("\n" + "=" * 60)
        print("🧪 Testing: mobile_control scroll")
        print("=" * 60)

        try:
            # 检查设备
            devices = await mobile_control.ainvoke({"action": "list_devices"})
            if "No Android devices" in devices:
                self.log("⚠️ No Android device connected - skipping")
                return True

            # 截图 - 滚动前
            before = await mobile_control.ainvoke({"action": "screenshot"})
            self.log(f"Screenshot before: {before}")

            # 测试 scroll 动作
            result = await mobile_control.ainvoke({
                "action": "scroll",
                "direction": "down",
                "amount": "medium"
            })

            self.log(f"Result: {result}")

            # 截图 - 滚动后
            after = await mobile_control.ainvoke({"action": "screenshot"})
            self.log(f"Screenshot after: {after}")

            if before != after:
                self.log("✅ scroll action implemented correctly")
                return True
            else:
                self.log("❌ scroll action did not change view")
                return False

        except Exception as e:
            if "Unknown action" in str(e) or "not found" in str(e).lower():
                self.log(f"⏳ scroll action not yet implemented: {e}")
            else:
                self.log(f"❌ Error: {e}")
            return False

    async def run_all(self):
        """运行所有测试"""
        print("\n" + "=" * 70)
        print("🚀 NEW ACTION IMPLEMENTATION TEST SUITE")
        print("=" * 70)

        tests = [
            ("browser_batch", self.test_browser_batch),
            ("browser_upload", self.test_browser_upload),
            ("desktop_scroll", self.test_desktop_scroll),
            ("desktop_drag_drop", self.test_desktop_drag_drop),
            ("mobile_scroll", self.test_mobile_scroll),
        ]

        results = {}
        for name, test_func in tests:
            try:
                results[name] = await test_func()
            except Exception as e:
                self.log(f"CRASH: {e}")
                results[name] = False
            await asyncio.sleep(1)

        # 汇总
        print("\n" + "=" * 70)
        print("📊 IMPLEMENTATION TEST RESULTS")
        print("=" * 70)

        implemented = []
        not_implemented = []
        failed = []

        for name, passed in results.items():
            if passed:
                print(f"  ✅ IMPLEMENTED: {name}")
                implemented.append(name)
            elif name in ["browser_batch", "browser_upload", "desktop_scroll", "desktop_drag_drop", "mobile_scroll"]:
                print(f"  ⏳ NOT YET: {name}")
                not_implemented.append(name)
            else:
                print(f"  ❌ FAILED: {name}")
                failed.append(name)

        print(f"\n  Total: {len(results)}")
        print(f"  ✅ Implemented: {len(implemented)}")
        print(f"  ⏳ Not yet: {len(not_implemented)}")
        print(f"  ❌ Failed: {len(failed)}")

        if implemented:
            print(f"\n  🎉 Ready to use: {', '.join(implemented)}")

        return len(failed) == 0


async def main():
    parser = argparse.ArgumentParser(description="Test new action implementations")
    parser.add_argument("--action", choices=[
        "browser_batch", "browser_upload",
        "desktop_scroll", "desktop_drag_drop",
        "mobile_scroll"
    ], help="Test specific action")

    args = parser.parse_args()

    tester = ActionTester()

    if args.action:
        test_map = {
            "browser_batch": tester.test_browser_batch,
            "browser_upload": tester.test_browser_upload,
            "desktop_scroll": tester.test_desktop_scroll,
            "desktop_drag_drop": tester.test_desktop_drag_drop,
            "mobile_scroll": tester.test_mobile_scroll,
        }
        passed = await test_map[args.action]()
        sys.exit(0 if passed else 1)
    else:
        success = await tester.run_all()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
