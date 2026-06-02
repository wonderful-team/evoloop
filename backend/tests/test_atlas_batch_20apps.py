#!/usr/bin/env python3
"""
Atlas Phase 6 批量应用测试（20+ 应用）

测试内容：
1. 批量打开 20+ 个 Android 和 macOS 应用
2. 验证每个应用的动态/静态分类
3. 验证 Atlas 存储策略
4. 生成详细的分类报告
"""

import asyncio
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.core.atlas import atlas_engine
from app.core.atlas.models import AtlasApp, AtlasElement, AtlasState
from app.core.atlas.strategy import AtlasStrategyStore
from app.core.environment.explorers.dynamic_apps import DynamicAppTriage
from app.domain.tools.environment.mobile import mobile_control
from app.domain.tools.environment.desktop import desktop_control
from app.infrastructure.drivers.adb import adb_driver, ADBError
from app.infrastructure.drivers.macos import macos_driver


@dataclass
class AppTestResult:
    """单个应用测试结果"""
    name: str
    bundle_id: str
    platform: str
    is_dynamic_expected: bool
    is_dynamic_detected: bool
    is_installed: bool
    open_success: bool
    ui_dump_size: int
    strategy_created: bool
    error: Optional[str] = None


class BatchAtlasTest:
    """批量 Atlas 测试"""

    # Android 测试应用列表（15个）
    ANDROID_APPS = [
        # 动态应用（聊天、社交、浏览器）
        ("com.tencent.mm", "微信", True),
        ("com.sina.weibo", "微博", True),
        ("com.taobao.taobao", "淘宝", True),
        ("com.xingin.xhs", "小红书", True),
        ("com.ss.android.ugc.aweme", "抖音", True),
        ("com.baidu.searchbox", "百度", True),
        ("com.android.browser", "浏览器", True),
        ("com.google.android.gm", "Gmail", True),

        # 静态应用（工具、设置）
        ("com.android.settings", "设置", False),
        ("com.android.calculator2", "计算器", False),
        ("com.android.deskclock", "时钟", False),
        ("com.android.contacts", "联系人", False),
        ("com.android.camera", "相机", False),
        ("com.android.gallery3d", "相册", False),
        ("com.huawei.systemmanager", "手机管家", False),
    ]

    # macOS 测试应用列表（10个）
    MACOS_APPS = [
        # 动态应用
        ("com.tencent.xinWeChat", "微信", True),
        ("com.apple.Safari", "Safari", True),
        ("com.google.Chrome", "Chrome", True),
        ("com.microsoft.Teams", "Teams", True),
        ("com.tinyspeck.slackmacgap", "Slack", True),
        ("com.apple.mail", "Mail", True),

        # 静态应用
        ("com.apple.systempreferences", "系统设置", False),
        ("com.apple.calculator", "计算器", False),
        ("com.apple.ActivityMonitor", "活动监视器", False),
        ("com.apple.Terminal", "终端", False),
    ]

    def __init__(self):
        self.results = []
        self.device_id = None
        self.has_android = False
        self.has_macos = True  # 默认有macOS

    async def run_all_tests(self):
        """运行所有批量测试"""
        print("\n" + "=" * 100)
        print("🔬 Atlas Phase 6 批量应用测试（20+ 应用）")
        print("=" * 100)
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"计划测试: {len(self.ANDROID_APPS)} 个 Android + {len(self.MACOS_APPS)} 个 macOS = {len(self.ANDROID_APPS) + len(self.MACOS_APPS)} 个应用\n")

        # 初始化
        await self._init()

        # 测试 Android 应用
        if self.has_android:
            print("\n" + "=" * 100)
            print("📱 Android 应用测试")
            print("=" * 100)
            for bundle_id, name, is_dynamic in self.ANDROID_APPS:
                await self._test_android_app(bundle_id, name, is_dynamic)
                await asyncio.sleep(1)  # 测试间隔

        # 测试 macOS 应用
        print("\n" + "=" * 100)
        print("🖥️  macOS 应用测试")
        print("=" * 100)
        for bundle_id, name, is_dynamic in self.MACOS_APPS:
            await self._test_macos_app(bundle_id, name, is_dynamic)
            await asyncio.sleep(1)  # 测试间隔

        # 生成报告
        self._print_summary()
        self._save_report()

    async def _init(self):
        """初始化测试环境"""
        print("📋 初始化测试环境...")

        # 检查 Android 设备
        try:
            devices = adb_driver.list_devices()
            if devices:
                self.has_android = True
                self.device_id = devices[0]['serial']
                print(f"  ✅ Android 设备: {devices[0].get('model', 'Unknown')}")
            else:
                print("  ⚠️  未检测到 Android 设备，跳过 Android 测试")
        except Exception as e:
            print(f"  ⚠️  Android 设备检查失败: {e}")

        # 检查 macOS 权限
        if macos_driver.check_accessibility_permission():
            print("  ✅ macOS 辅助功能权限")
        else:
            print("  ⚠️  macOS 辅助功能权限未授予")
            self.has_macos = False

    async def _test_android_app(self, bundle_id: str, name: str, is_dynamic_expected: bool):
        """测试单个 Android 应用"""
        print(f"\n测试: {name} ({bundle_id})")
        print("-" * 80)

        result = AppTestResult(
            name=name,
            bundle_id=bundle_id,
            platform="android",
            is_dynamic_expected=is_dynamic_expected,
            is_dynamic_detected=False,
            is_installed=False,
            open_success=False,
            ui_dump_size=0,
            strategy_created=False
        )

        try:
            # Step 1: 检查是否安装
            print("  Step 1: 检查安装状态...")
            try:
                apps = adb_driver.list_installed_apps(device_id=self.device_id)
                result.is_installed = bundle_id in apps
            except:
                result.is_installed = True  # 假设已安装，让后续步骤确认

            if not result.is_installed:
                print(f"    ⚠️  应用未安装，跳过")
                result.error = "Not installed"
                self.results.append(result)
                return
            print(f"    ✅ 已安装")

            # Step 2: 动态应用检测
            print("  Step 2: 动态应用检测...")
            result.is_dynamic_detected = await atlas_engine.is_dynamic_app(bundle_id, "android")
            icon = "🔄" if result.is_dynamic_detected else "📍"
            print(f"    {icon} 检测结果: {'动态' if result.is_dynamic_detected else '静态'}")

            # 验证预期
            if result.is_dynamic_detected == is_dynamic_expected:
                print(f"    ✅ 符合预期")
            else:
                print(f"    ⚠️  不符合预期 (预期: {'动态' if is_dynamic_expected else '静态'})")

            # Step 3: 打开应用
            print("  Step 3: 打开应用...")
            try:
                open_result = await mobile_control.ainvoke({
                    "action": "open_app",
                    "text": bundle_id
                })
                if "Error" in str(open_result) or "⚠️" in str(open_result):
                    print(f"    ⚠️  打开失败: {open_result[:100]}")
                    result.error = f"Open failed: {open_result[:100]}"
                else:
                    result.open_success = True
                    print(f"    ✅ 打开成功")
                    await asyncio.sleep(2)  # 等待应用加载
            except Exception as e:
                print(f"    ❌ 打开异常: {e}")
                result.error = str(e)

            # Step 4: Dump UI
            if result.open_success:
                print("  Step 4: Dump UI...")
                try:
                    ui_result = await mobile_control.ainvoke({
                        "action": "dump_ui"
                    })
                    result.ui_dump_size = len(str(ui_result))
                    print(f"    UI 大小: {result.ui_dump_size} bytes")

                    # 检查是否为空的 UI dump（如微信）
                    if result.ui_dump_size < 1000:
                        print(f"    ⚠️  UI dump 较短（可能自定义渲染）")
                except Exception as e:
                    print(f"    ❌ Dump UI 失败: {e}")

            # Step 5: 检查策略
            print("  Step 5: 检查策略...")
            strategy = await atlas_engine.get_app_strategy(bundle_id)
            if strategy:
                result.strategy_created = True
                infra_count = len(strategy.infrastructure)
                strat_count = len(strategy.strategies)
                print(f"    ✅ 策略存在: {infra_count} 基础设施, {strat_count} 策略")
            else:
                print(f"    ○ 暂无策略")

        except Exception as e:
            print(f"  ❌ 测试异常: {e}")
            result.error = str(e)

        self.results.append(result)

    async def _test_macos_app(self, bundle_id: str, name: str, is_dynamic_expected: bool):
        """测试单个 macOS 应用"""
        print(f"\n测试: {name} ({bundle_id})")
        print("-" * 80)

        result = AppTestResult(
            name=name,
            bundle_id=bundle_id,
            platform="macos",
            is_dynamic_expected=is_dynamic_expected,
            is_dynamic_detected=False,
            is_installed=True,  # 假设已安装
            open_success=False,
            ui_dump_size=0,
            strategy_created=False
        )

        try:
            # Step 1: 动态应用检测
            print("  Step 1: 动态应用检测...")
            result.is_dynamic_detected = await atlas_engine.is_dynamic_app(bundle_id, "android")
            icon = "🔄" if result.is_dynamic_detected else "📍"
            print(f"    {icon} 检测结果: {'动态' if result.is_dynamic_detected else '静态'}")

            # 验证预期
            if result.is_dynamic_detected == is_dynamic_expected:
                print(f"    ✅ 符合预期")
            else:
                print(f"    ⚠️  不符合预期 (预期: {'动态' if is_dynamic_expected else '静态'})")

            # Step 2: 打开应用
            print("  Step 2: 打开应用...")
            try:
                open_result = await desktop_control.ainvoke({
                    "action": "open_app",
                    "app_name": name
                })
                if "Error" in str(open_result) or "WARNING" in str(open_result):
                    print(f"    ⚠️  打开警告: {open_result[:100]}")
                    # 继续测试，可能应用已在后台
                else:
                    result.open_success = True
                    print(f"    ✅ 打开成功")
                    await asyncio.sleep(2)
            except Exception as e:
                print(f"    ❌ 打开异常: {e}")
                result.error = str(e)

            # Step 3: 获取 AX Tree
            print("  Step 3: 获取 AX Tree...")
            try:
                ax_output = macos_driver.dump_ax_tree()
                if ax_output and "Error" not in ax_output:
                    result.ui_dump_size = len(ax_output)
                    element_count = len(ax_output.split("}, {"))
                    print(f"    AX 元素数: ~{element_count}")
                else:
                    print(f"    ⚠️  AX Tree 获取失败")
            except Exception as e:
                print(f"    ❌ AX Tree 异常: {e}")

            # Step 4: 检查策略
            print("  Step 4: 检查策略...")
            strategy = await atlas_engine.get_app_strategy(bundle_id)
            if strategy:
                result.strategy_created = True
                infra_count = len(strategy.infrastructure)
                strat_count = len(strategy.strategies)
                print(f"    ✅ 策略存在: {infra_count} 基础设施, {strat_count} 策略")
            else:
                print(f"    ○ 暂无策略")

        except Exception as e:
            print(f"  ❌ 测试异常: {e}")
            result.error = str(e)

        self.results.append(result)

    def _print_summary(self):
        """打印测试汇总"""
        print("\n" + "=" * 100)
        print("📊 批量测试汇总报告")
        print("=" * 100)

        android_results = [r for r in self.results if r.platform == "android"]
        macos_results = [r for r in self.results if r.platform == "macos"]

        # Android 汇总
        if android_results:
            print(f"\n📱 Android 应用 ({len(android_results)} 个):")
            print("-" * 100)
            print(f"{'应用名称':<15} {'Bundle ID':<35} {'预期':<6} {'检测':<6} {'安装':<6} {'打开':<6} {'UI大小':<10} {'策略':<6} {'状态':<10}")
            print("-" * 100)

            for r in android_results:
                status = "✅" if r.is_dynamic_detected == r.is_dynamic_expected else "⚠️"
                installed = "✅" if r.is_installed else "❌"
                opened = "✅" if r.open_success else "❌"
                strategy = "✅" if r.strategy_created else "○"

                print(f"{r.name:<15} {r.bundle_id:<35} "
                      f"{'动' if r.is_dynamic_expected else '静':<6} "
                      f"{'动' if r.is_dynamic_detected else '静':<6} "
                      f"{installed:<6} {opened:<6} "
                      f"{r.ui_dump_size:<10} {strategy:<6} {status:<10}")

            # 统计
            correct = sum(1 for r in android_results if r.is_dynamic_detected == r.is_dynamic_expected)
            print(f"\n  Android 分类准确率: {correct}/{len(android_results)} ({correct/len(android_results)*100:.1f}%)")

        # macOS 汇总
        if macos_results:
            print(f"\n🖥️  macOS 应用 ({len(macos_results)} 个):")
            print("-" * 100)
            print(f"{'应用名称':<15} {'Bundle ID':<35} {'预期':<6} {'检测':<6} {'打开':<6} {'AX元素':<10} {'策略':<6} {'状态':<10}")
            print("-" * 100)

            for r in macos_results:
                status = "✅" if r.is_dynamic_detected == r.is_dynamic_expected else "⚠️"
                opened = "✅" if r.open_success else "❌"
                strategy = "✅" if r.strategy_created else "○"
                ax_size = f"~{r.ui_dump_size//100}" if r.ui_dump_size > 0 else "N/A"

                print(f"{r.name:<15} {r.bundle_id:<35} "
                      f"{'动' if r.is_dynamic_expected else '静':<6} "
                      f"{'动' if r.is_dynamic_detected else '静':<6} "
                      f"{opened:<6} {ax_size:<10} {strategy:<6} {status:<10}")

            # 统计
            correct = sum(1 for r in macos_results if r.is_dynamic_detected == r.is_dynamic_expected)
            print(f"\n  macOS 分类准确率: {correct}/{len(macos_results)} ({correct/len(macos_results)*100:.1f}%)")

        # 总体统计
        print("\n" + "=" * 100)
        total = len(self.results)
        total_correct = sum(1 for r in self.results if r.is_dynamic_detected == r.is_dynamic_expected)
        print(f"总计测试: {total} 个应用")
        print(f"分类准确: {total_correct}/{total} ({total_correct/total*100:.1f}%)")

        # 动态 vs 静态统计
        dynamic_count = sum(1 for r in self.results if r.is_dynamic_detected)
        static_count = total - dynamic_count
        print(f"动态应用: {dynamic_count} 个")
        print(f"静态应用: {static_count} 个")

        # 策略统计
        with_strategy = sum(1 for r in self.results if r.strategy_created)
        print(f"有策略的: {with_strategy} 个")

        print("\n" + "=" * 100)

    def _save_report(self):
        """保存测试报告到文件"""
        report_file = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/scripts/atlas_batch_test_report.txt"

        with open(report_file, 'w') as f:
            f.write("Atlas Phase 6 批量测试报告\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 100 + "\n\n")

            for r in self.results:
                f.write(f"应用: {r.name} ({r.bundle_id})\n")
                f.write(f"  平台: {r.platform}\n")
                f.write(f"  预期: {'动态' if r.is_dynamic_expected else '静态'}\n")
                f.write(f"  检测: {'动态' if r.is_dynamic_detected else '静态'}\n")
                f.write(f"  安装: {'是' if r.is_installed else '否'}\n")
                f.write(f"  打开: {'成功' if r.open_success else '失败'}\n")
                f.write(f"  UI大小: {r.ui_dump_size} bytes\n")
                f.write(f"  策略: {'已创建' if r.strategy_created else '无'}\n")
                if r.error:
                    f.write(f"  错误: {r.error}\n")
                f.write("\n")

        print(f"\n📄 详细报告已保存: {report_file}")


async def main():
    test = BatchAtlasTest()
    await test.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
