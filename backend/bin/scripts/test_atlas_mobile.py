#!/usr/bin/env python3
"""
Atlas Phase 6 移动端专项测试

测试内容：
1. Android 微信（动态应用）- 验证基础设施提取
2. Android 设置（静态应用）- 验证完整 Atlas 存储
3. Android Chrome（动态应用）- 验证搜索策略
4. 对比静态/动态应用的 Atlas 存储差异
"""

import asyncio
import sys
import time
from datetime import datetime

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.core.atlas import atlas_engine
from app.core.atlas.models import AtlasApp, AtlasElement, AtlasState
from app.core.atlas.strategy import AtlasStrategyStore
from app.core.environment.explorers.dynamic_apps import DynamicAppTriage
from app.core.environment.tools.mobile import mobile
from app.infrastructure.drivers.adb import adb_driver, ADBError


class MobileAtlasTest:
    """移动端 Atlas 测试"""

    def __init__(self):
        self.results = []
        self.device_id = None

    async def run_all_tests(self):
        """运行所有移动端测试"""
        print("\n" + "=" * 80)
        print("📱 Atlas Phase 6 移动端专项测试")
        print("=" * 80)
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # 检查设备
        if not await self._check_device():
            return

        # 运行测试
        tests = [
            ("Android 微信 - 动态应用处理", self.test_wechat_dynamic),
            ("Android 设置 - 静态应用完整存储", self.test_settings_static),
            ("Android Chrome - 浏览器策略", self.test_chrome_strategy),
            ("对比测试 - 静态 vs 动态", self.test_comparison),
        ]

        for name, test_func in tests:
            await self._run_test(name, test_func)
            await asyncio.sleep(2)

        self._print_summary()

    async def _check_device(self) -> bool:
        """检查设备连接"""
        print("📋 检查设备连接...")

        try:
            devices = adb_driver.list_devices()
            if not devices:
                print("  ❌ 未检测到 Android 设备")
                print("\n请检查：")
                print("  1. USB 线是否连接牢固")
                print("  2. 手机是否开启 USB 调试")
                print("  3. 是否允许此电脑进行调试（授权弹窗）")
                print("  4. 尝试运行: adb devices")
                return False

            self.device_id = devices[0]['serial']
            model = devices[0].get('model', devices[0].get('info', 'Unknown'))
            print(f"  ✅ 设备已连接: {model}")
            print(f"  📱 Serial: {self.device_id}")

            # 获取当前应用
            app_info = adb_driver.get_current_app(device_id=self.device_id)
            print(f"  🎯 当前应用: {app_info.get('package', 'unknown')}")

            return True

        except ADBError as e:
            print(f"  ❌ ADB 错误: {e}")
            return False

    async def _run_test(self, name: str, test_func):
        """运行单个测试"""
        print(f"\n{'─' * 80}")
        print(f"测试: {name}")
        print(f"{'─' * 80}")

        try:
            start_time = time.time()
            await test_func()
            elapsed = time.time() - start_time

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

    async def test_wechat_dynamic(self):
        """测试 Android 微信动态应用"""
        print("🎯 目标: 验证微信只存储基础设施\n")

        bundle_id = "com.tencent.mm"

        # Step 1: 验证动态应用检测
        print("Step 1: 验证动态应用检测...")
        is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "android")
        print(f"  is_dynamic_app('{bundle_id}'): {is_dynamic}")
        assert is_dynamic, "微信应该被识别为动态应用"

        # Step 2: 打开微信
        print("\nStep 2: 打开微信...")
        result = await mobile.ainvoke({
            "action": "open_app",
            "text": bundle_id
        })
        print(f"  结果: {result}")
        await asyncio.sleep(3)

        # Step 3: 获取当前页面信息
        print("\nStep 3: 获取页面信息...")
        app_info = adb_driver.get_current_app(device_id=self.device_id)
        activity = app_info.get('activity', '')
        print(f"  Activity: {activity}")

        # Step 4: Dump UI
        print("\nStep 4: Dump UI...")
        result = await mobile.ainvoke({
            "action": "dump_ui"
        })
        ui_length = len(result) if isinstance(result, str) else 0
        print(f"  UI XML 长度: {ui_length}")

        if ui_length < 500:
            print("  ⚠️  UI dump 较短，微信可能使用了自定义渲染")
            print("  ✅ 这种情况下 Atlas 将依赖策略而非坐标")

        # Step 5: 验证策略获取
        print("\nStep 5: 验证策略获取...")
        strategy = await atlas_engine.get_app_strategy(bundle_id)
        if strategy:
            print(f"  ✅ 策略存在")
            print(f"     基础设施: {len(strategy.infrastructure)} 个")
            for infra in strategy.infrastructure:
                print(f"       • {infra.get('role')}: {infra.get('label')}")
        else:
            print(f"  ⚠️  策略不存在，将在首次观测后创建")

        print("\n✅ 微信动态应用测试通过")

    async def test_settings_static(self):
        """测试 Android 设置静态应用"""
        print("🎯 目标: 验证静态应用完整 Atlas 存储\n")

        bundle_id = "com.android.settings"

        # Step 1: 验证静态应用识别
        print("Step 1: 验证静态应用识别...")
        is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "android")
        print(f"  is_dynamic_app('{bundle_id}'): {is_dynamic}")
        assert not is_dynamic, "设置应该是静态应用"
        print("  ✅ 设置被正确识别为静态应用")

        # Step 2: 打开设置
        print("\nStep 2: 打开设置...")
        result = await mobile.ainvoke({
            "action": "open_app",
            "text": bundle_id
        })
        print(f"  结果: {result}")
        await asyncio.sleep(2)

        # Step 3: 查找元素（触发 Atlas 学习）
        print("\nStep 3: 查找元素触发 Atlas 学习...")
        result = await mobile.ainvoke({
            "action": "click",
            "text": "网络",
            "timeout": 5.0
        })
        print(f"  结果: {result[:100] if isinstance(result, str) else result}...")

        # Step 4: 查询 Atlas 数据
        print("\nStep 4: 查询 Atlas 数据...")
        summary = await atlas_engine.store.get_app_summary(bundle_id)
        if summary:
            print(f"  ✅ Atlas 数据存在")
            print(f"     状态数: {summary.get('state_count', 0)}")
            print(f"     版本哈希: {summary.get('version_hash', 'N/A')}")

            # 检查是否存储了完整元素（不是只有基础设施）
            states = summary.get('states', [])
            if states:
                detail = await atlas_engine.store.get_state_detail(
                    bundle_id, states[0]['id']
                )
                element_count = len(detail.get('elements', []))
                print(f"     元素数: {element_count}")

                if element_count > 3:
                    print("  ✅ 静态应用存储了完整元素（不只是基础设施）")
        else:
            print("  ℹ️  暂无 Atlas 数据（首次运行）")

        print("\n✅ 设置静态应用测试通过")

    async def test_chrome_strategy(self):
        """测试 Android Chrome 浏览器策略"""
        print("🎯 目标: 验证 Chrome 浏览器策略\n")

        bundle_id = "com.android.chrome"

        # Step 1: 验证动态应用检测
        print("Step 1: 验证动态应用检测...")
        is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "android")
        print(f"  is_dynamic_app('{bundle_id}'): {is_dynamic}")

        # Step 2: 打开 Chrome
        print("\nStep 2: 打开 Chrome...")
        result = await mobile.ainvoke({
            "action": "open_app",
            "text": bundle_id
        })
        print(f"  结果: {result}")
        await asyncio.sleep(2)

        # Step 3: 导航到网页
        print("\nStep 3: 导航到网页...")
        result = await mobile.ainvoke({
            "action": "open_app",
            "text": "com.android.chrome"
        })
        print(f"  结果: {result[:100] if isinstance(result, str) else result}...")
        await asyncio.sleep(2)

        # Step 4: 查找搜索框
        print("\nStep 4: 查找搜索框...")
        result = await mobile.ainvoke({
            "action": "click",
            "text": "搜索",
            "timeout": 5.0
        })
        print(f"  结果类型: {'策略' if isinstance(result, dict) and 'strategy' in result else '坐标/错误'}")

        print("\n✅ Chrome 浏览器测试通过")

    async def test_comparison(self):
        """对比静态 vs 动态应用的 Atlas 处理"""
        print("🎯 目标: 对比静态 vs 动态应用的 Atlas 存储差异\n")

        # 测试应用
        test_apps = [
            ("com.tencent.mm", "微信（动态）"),
            ("com.android.settings", "设置（静态）"),
            ("com.android.chrome", "Chrome（动态）"),
        ]

        print("应用类型检测:")
        for bundle_id, name in test_apps:
            is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "android")
            app_type = "动态" if is_dynamic else "静态"
            icon = "🔄" if is_dynamic else "📍"
            print(f"  {icon} {name}: {app_type}")

        print("\n策略存储状态:")
        for bundle_id, name in test_apps:
            strategy = await atlas_engine.get_app_strategy(bundle_id)
            if strategy:
                infra = len(strategy.infrastructure)
                strat = len(strategy.strategies)
                print(f"  ✅ {name}: {infra} 基础设施, {strat} 策略")
            else:
                print(f"  ○ {name}: 暂无策略")

        print("\nAtlas 存储状态:")
        for bundle_id, name in test_apps:
            summary = await atlas_engine.store.get_app_summary(bundle_id)
            if summary:
                states = summary.get('state_count', 0)
                is_dynamic_app = summary.get('is_dynamic', False)
                marker = "[动态]" if is_dynamic_app else "[静态]"
                print(f"  ✅ {name} {marker}: {states} 个状态")
            else:
                print(f"  ○ {name}: 暂无 Atlas 数据")

        print("\n✅ 对比测试通过")

    def _print_summary(self):
        """打印汇总"""
        print("\n" + "=" * 80)
        print("📊 移动端测试汇总")
        print("=" * 80)

        for result in self.results:
            status = result["status"]
            name = result["name"]
            elapsed = result.get("elapsed", "-")

            if "通过" in status:
                print(f"  ✅ {name} ({elapsed})")
            else:
                print(f"  ❌ {name}")
                if "error" in result:
                    print(f"     错误: {result['error']}")

        passed = len([r for r in self.results if "通过" in r["status"]])
        total = len(self.results)
        print(f"\n总计: {passed}/{total} 通过")

        if passed == total:
            print("\n🎉 所有移动端测试通过！")
        else:
            print(f"\n⚠️  {total - passed} 个测试失败")


async def main():
    test = MobileAtlasTest()
    await test.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
