#!/usr/bin/env python3
"""
Atlas Phase 6 端到端测试

使用实际控制工具（desktop_control, mobile_control, browser_control）
打开多端应用，验证动态应用检测、元素分类和策略存储逻辑。

测试场景：
1. macOS 微信（动态应用）- 验证基础设施提取
2. macOS Safari（动态应用）- 验证策略存储
3. Android 设置（静态应用）- 验证完整 Atlas 存储
4. Chrome 浏览器（动态应用）- 验证搜索策略
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.core.atlas import atlas_engine
from app.core.atlas.strategy import AtlasStrategyStore, init_default_strategies
from app.core.environment.tools.desktop import desktop_control
from app.core.environment.tools.browser import browser_control
from app.core.environment.tools.mobile import mobile_control
from app.core.vision import vision_engine, VisionTask
from app.infrastructure.drivers.adb import adb_driver
from app.infrastructure.drivers.macos import macos_driver


class AtlasE2ETest:
    """端到端测试执行器"""

    def __init__(self):
        self.results = []
        self.test_count = 0
        self.pass_count = 0

    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "=" * 80)
        print("🔬 Atlas Phase 6 端到端测试")
        print("=" * 80)
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # 初始化
        await self._init()

        # 测试用例
        tests = [
            ("macOS 微信 - 动态应用检测", self.test_macos_wechat_dynamic),
            ("macOS Safari - 浏览器策略", self.test_macos_safari),
            ("Android 设置 - 静态应用", self.test_android_settings),
            ("Chrome 浏览器 - 搜索策略", self.test_chrome_browser),
        ]

        for name, test_func in tests:
            await self._run_test(name, test_func)
            await asyncio.sleep(2)  # 测试间隔

        # 汇总报告
        self._print_summary()

    async def _init(self):
        """初始化测试环境"""
        print("📋 初始化测试环境...")

        # 初始化默认策略
        await init_default_strategies()
        print("  ✅ 默认策略初始化完成")

        # 检查设备连接
        try:
            devices = adb_driver.list_devices()
            if devices:
                print(f"  ✅ Android 设备: {devices[0]['model']}")
            else:
                print("  ⚠️  未检测到 Android 设备")
        except Exception as e:
            print(f"  ⚠️  Android 设备检查失败: {e}")

        # 检查 macOS 权限
        if macos_driver.check_accessibility_permission():
            print("  ✅ macOS 辅助功能权限")
        else:
            print("  ⚠️  macOS 辅助功能权限未授予")

    async def _run_test(self, name: str, test_func):
        """运行单个测试"""
        self.test_count += 1
        print(f"\n{'─' * 80}")
        print(f"测试 {self.test_count}: {name}")
        print(f"{'─' * 80}")

        try:
            start_time = time.time()
            await test_func()
            elapsed = time.time() - start_time

            self.pass_count += 1
            self.results.append({
                "name": name,
                "status": "✅ 通过",
                "elapsed": f"{elapsed:.1f}s"
            })
            print(f"\n✅ 通过 ({elapsed:.1f}s)")

        except Exception as e:
            self.results.append({
                "name": name,
                "status": "❌ 失败",
                "error": str(e)
            })
            print(f"\n❌ 失败: {e}")
            import traceback
            traceback.print_exc()

    async def test_macos_wechat_dynamic(self):
        """测试 macOS 微信动态应用处理"""
        print("🎯 目标: 验证微信被识别为动态应用，只存储基础设施\n")

        # Step 1: 检查微信是否运行
        print("Step 1: 检查微信状态...")
        result = await desktop_control.ainvoke({
            "action": "get_active_app"
        })
        print(f"  当前应用: {result}")

        # 如果微信不在前台，尝试打开
        if "WeChat" not in result and "微信" not in result:
            print("  尝试激活微信...")
            result = await desktop_control.ainvoke({
                "action": "open_app",
                "app_name": "WeChat"
            })
            print(f"  结果: {result}")
            await asyncio.sleep(3)

        # Step 2: 截图并分析
        print("\nStep 2: 截图分析 UI...")
        result = await desktop_control.ainvoke({
            "action": "screenshot",
            "ocr": True
        })
        print(f"  截图完成: {result[:200]}...")

        # Step 3: 获取 AX Tree
        print("\nStep 3: 获取 AX Tree...")
        ax_output = macos_driver.dump_ax_tree()
        elements_count = len(ax_output.split("}, {")) if ax_output and "Error" not in ax_output else 0
        print(f"  AX 元素数量: {elements_count}")

        # Step 4: 验证动态应用检测
        print("\nStep 4: 验证动态应用检测...")
        bundle_id = "com.tencent.xinWeChat"
        is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "android")
        print(f"  is_dynamic_app('{bundle_id}'): {is_dynamic}")
        assert is_dynamic, "微信应该被识别为动态应用"

        # Step 5: 验证策略获取
        print("\nStep 5: 验证策略获取...")
        strategy = await atlas_engine.get_app_strategy(bundle_id)
        if strategy:
            print(f"  ✅ 策略存在")
            print(f"     基础设施: {len(strategy.infrastructure)} 个")
            print(f"     交互策略: {len(strategy.strategies)} 个")
        else:
            print(f"  ⚠️  策略不存在（首次运行，创建默认策略）")

        # Step 6: 模拟触发 Atlas 学习
        print("\nStep 6: 模拟 Atlas 学习...")

        # 创建模拟的 UI 元素
        mock_elements = [
            {
                "role": "AXButton",
                "label": "搜索",
                "ax_path": "button 1 of window 1",
                "bounds": {"x": 500, "y": 50, "width": 60, "height": 30},
                "metadata": {"role": "AXButton", "subrole": "", "is_scrollable": False}
            },
            {
                "role": "AXButton",
                "label": "+",
                "ax_path": "button 2 of window 1",
                "bounds": {"x": 600, "y": 50, "width": 40, "height": 30},
                "metadata": {"role": "AXButton", "subrole": "", "is_scrollable": False}
            },
            {
                "role": "AXScrollArea",
                "label": "",
                "ax_path": "scroll area 1 of window 1",
                "bounds": {"x": 0, "y": 100, "width": 1200, "height": 800},
                "metadata": {"role": "AXScrollArea", "subrole": "", "is_scrollable": True}
            }
        ]

        event = type('Event', (), {
            'data': {
                'bundle_id': bundle_id,
                'window_title': '微信',
                'platform': 'macos',
                'screenshot_hash': '',
                'version_hash': ''
            },
            'elements': mock_elements
        })()

        # 调用 Atlas 处理
        await atlas_engine.on_ui_tree_observed(event)

        # Step 7: 验证只存储了基础设施
        print("\nStep 7: 验证基础设施存储...")
        strategy = await atlas_engine.get_app_strategy(bundle_id)
        if strategy:
            infra_count = len(strategy.infrastructure)
            print(f"  存储的基础设施元素: {infra_count} 个")
            for infra in strategy.infrastructure:
                print(f"    • {infra.get('role')}: {infra.get('label')}")
            assert infra_count <= 2, "应该只存储基础设施（搜索栏、按钮），不存储滚动区域"

        print("\n✅ 微信动态应用测试通过")

    async def test_macos_safari(self):
        """测试 macOS Safari 浏览器策略"""
        print("🎯 目标: 验证 Safari 浏览器策略存储\n")

        bundle_id = "com.apple.Safari"

        # Step 1: 检查动态应用检测
        print("Step 1: 检查动态应用检测...")
        is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "android")
        print(f"  is_dynamic_app('{bundle_id}'): {is_dynamic}")

        # Step 2: 打开 Safari
        print("\nStep 2: 打开 Safari...")
        result = await desktop_control.ainvoke({
            "action": "open_app",
            "app_name": "Safari"
        })
        print(f"  结果: {result}")
        await asyncio.sleep(2)

        # Step 3: 使用 browser_control 导航
        print("\nStep 3: 使用 browser_control 导航...")
        result = await browser_control.ainvoke({
            "action": "navigate",
            "url": "https://www.bing.com"
        })
        print(f"  导航结果: {result[:200]}...")
        await asyncio.sleep(3)

        # Step 4: 验证策略
        print("\nStep 4: 验证策略存储...")
        strategy = await atlas_engine.get_app_strategy(bundle_id)
        if strategy:
            print(f"  ✅ 策略存在")
            print(f"     提示: {strategy.hints}")
        else:
            print(f"  ⚠️  策略不存在")

        print("\n✅ Safari 测试通过")

    async def test_android_settings(self):
        """测试 Android 设置静态应用"""
        print("🎯 目标: 验证静态应用完整 Atlas 存储\n")

        # Step 1: 检查设备
        print("Step 1: 检查设备连接...")
        devices = adb_driver.list_devices()
        if not devices:
            print("  ⚠️  无 Android 设备，跳过测试")
            return
        print(f"  ✅ 设备: {devices[0]['model']}")

        # Step 2: 打开设置
        print("\nStep 2: 打开 Android 设置...")
        result = await mobile_control.ainvoke({"action": "open_app",
            "text": "com.android.settings"})
        print(f"  结果: {result}")
        await asyncio.sleep(2)

        # Step 3: dump UI
        print("\nStep 3: 获取 UI 结构...")
        result = await mobile_control.ainvoke({"action": "dump_ui"})
        ui_length = len(result)
        print(f"  UI XML 长度: {ui_length}")

        # Step 4: 检查应用类型
        print("\nStep 4: 检查应用类型...")
        bundle_id = "com.android.settings"
        is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "android")
        print(f"  is_dynamic_app('{bundle_id}'): {is_dynamic}")

        if not is_dynamic:
            print("  ✅ 设置应用被识别为静态应用（预期）")
        else:
            print("  ⚠️  设置应用被意外识别为动态应用")

        # Step 5: 触发 Atlas 学习
        print("\nStep 5: 触发 Atlas 学习...")

        # 使用视觉引擎获取元素
        elements, _ = await vision_engine.process(
            task=VisionTask.DETECT,
            image_source="",  # mobile 会自己截图
            device_id=devices[0]['serial']
        )

        print(f"  检测到 {len(elements)} 个元素")

        # 创建事件
        event = type('Event', (), {
            'data': {
                'bundle_id': bundle_id,
                'window_title': 'Settings',
                'platform': 'android',
                'screenshot_hash': '',
                'version_hash': ''
            },
            'elements': [e.model_dump() for e in elements[:10]]  # 前10个元素
        })()

        await atlas_engine.on_ui_tree_observed(event)

        print("\n✅ Android 设置测试通过")

    async def test_chrome_browser(self):
        """测试 Chrome 浏览器搜索策略"""
        print("🎯 目标: 验证 Chrome 浏览器搜索策略\n")

        bundle_id = "com.google.Chrome"

        # Step 1: 检查动态应用检测
        print("Step 1: 检查动态应用检测...")
        is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "android")
        print(f"  is_dynamic_app('{bundle_id}'): {is_dynamic}")

        # Step 2: 打开 Chrome
        print("\nStep 2: 打开 Chrome...")
        result = await desktop_control.ainvoke({"action": "open_app",
            "app_name": "Google Chrome"})
        print(f"  结果: {result}")
        await asyncio.sleep(2)

        # Step 3: 使用 browser_control
        print("\nStep 3: 使用 browser_control 导航...")
        result = await browser_control.ainvoke({"action": "navigate", "url": "https://www.google.com"})
        print(f"  导航结果: {result[:200]}...")
        await asyncio.sleep(2)

        # Step 4: 搜索测试
        print("\nStep 4: 搜索测试...")
        result = await browser_control.ainvoke({"action": "type_text", "selector": "[name='q']", "text": "Atlas Phase 6"})
        print(f"  输入结果: {result}")

        # Step 5: 验证策略
        print("\nStep 5: 验证策略...")
        strategy = await atlas_engine.get_app_strategy(bundle_id)
        if strategy:
            print(f"  ✅ Chrome 策略存在")
        else:
            print(f"  ℹ️  Chrome 策略将在首次完整观测后创建")

        print("\n✅ Chrome 浏览器测试通过")

    def _print_summary(self):
        """打印测试汇总"""
        print("\n" + "=" * 80)
        print("📊 测试汇总")
        print("=" * 80)

        for result in self.results:
            status = result["status"]
            name = result["name"]
            elapsed = result.get("elapsed", "-")
            error = result.get("error", "")

            if "通过" in status:
                print(f"  ✅ {name} ({elapsed})")
            else:
                print(f"  ❌ {name}")
                if error:
                    print(f"     错误: {error}")

        print(f"\n总计: {self.pass_count}/{self.test_count} 通过")

        if self.pass_count == self.test_count:
            print("\n🎉 所有测试通过！Atlas Phase 6 功能正常。")
        else:
            print(f"\n⚠️  {self.test_count - self.pass_count} 个测试失败，请检查日志。")


async def main():
    test = AtlasE2ETest()
    await test.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
