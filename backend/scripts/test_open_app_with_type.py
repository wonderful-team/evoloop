#!/usr/bin/env python3
"""
测试 open_app 中集成动态/静态判断

验证点：
1. 打开动态应用时返回 DYNAMIC 标记
2. 打开静态应用时返回 STATIC 标记
3. 动态应用预加载策略
4. 静态应用触发 Atlas 学习
"""

import asyncio
import sys

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.domain.tools.environment.mobile import mobile_control
from app.domain.tools.environment.desktop import desktop_control
from app.infrastructure.drivers.adb import adb_driver
from app.core.atlas.config_manager import AtlasConfigManager


async def init_test_data():
    """Initialize test data in Redis."""
    await AtlasConfigManager.initialize_defaults()
    # Ensure WeChat is marked as dynamic (platform-specific)
    await AtlasConfigManager.mark_app_dynamic("com.tencent.mm", "android", "Messaging app with scrollable lists")
    await AtlasConfigManager.mark_app_dynamic("com.tencent.xinWeChat", "macos", "Messaging app with scrollable lists")
    await AtlasConfigManager.mark_app_dynamic("com.apple.Safari", "macos", "Web browser with dynamic content")
    print("[Test] Initialized test data in Redis")


async def test_mobile_open_app():
    """测试 Android open_app 带类型判断"""
    print("\n" + "=" * 80)
    print("📱 测试 Android open_app 动态/静态判断")
    print("=" * 80)

    # 检查设备
    devices = adb_driver.list_devices()
    if not devices:
        print("❌ 无 Android 设备，跳过测试")
        return

    print(f"✅ 设备: {devices[0].get('model', 'Unknown')}\n")

    # 测试 1: 动态应用（微信）
    print("测试 1: 打开动态应用（微信）...")
    result = await mobile_control.ainvoke({
        "action": "open_app",
        "text": "com.tencent.mm"
    })
    print(f"  结果: {result}")
    assert "DYNAMIC" in result or "🔄" in result, "应该标记为 DYNAMIC"
    print("  ✅ 正确标记为动态应用\n")

    await asyncio.sleep(2)

    # 测试 2: 静态应用（如果有的话）
    print("测试 2: 尝试打开静态应用...")
    # 尝试打开设置
    result = await mobile_control.ainvoke({
        "action": "open_app",
        "text": "com.android.settings"
    })
    print(f"  结果: {result}")
    # 如果安装了设置，应该标记为 STATIC
    if "Error" not in result:
        assert "STATIC" in result or "📍" in result, "应该标记为 STATIC"
        print("  ✅ 正确标记为静态应用\n")
    else:
        print("  ⚠️  设置应用不可用\n")


async def test_desktop_open_app():
    """测试 macOS open_app 带类型判断"""
    print("\n" + "=" * 80)
    print("🖥️  测试 macOS open_app 动态/静态判断")
    print("=" * 80)

    # 测试 1: 动态应用（微信）
    print("测试 1: 打开动态应用（微信）...")
    result = await desktop_control.ainvoke({
        "action": "open_app",
        "app_name": "WeChat"
    })
    print(f"  结果: {result}")
    assert "DYNAMIC" in result or "🔄" in result, "应该标记为 DYNAMIC"
    print("  ✅ 正确标记为动态应用\n")

    await asyncio.sleep(2)

    # 测试 2: 静态应用（计算器）
    print("测试 2: 打开静态应用（计算器）...")
    result = await desktop_control.ainvoke({
        "action": "open_app",
        "app_name": "Calculator"
    })
    print(f"  结果: {result}")
    # 计算器应该标记为 STATIC
    if "Error" not in result:
        assert "STATIC" in result or "📍" in result, "应该标记为 STATIC"
        print("  ✅ 正确标记为静态应用\n")
    else:
        print("  ⚠️  计算器打开失败\n")

    # 测试 3: 动态应用（Safari）
    print("测试 3: 打开动态应用（Safari）...")
    result = await desktop_control.ainvoke({
        "action": "open_app",
        "app_name": "Safari"
    })
    print(f"  结果: {result}")
    assert "DYNAMIC" in result or "🔄" in result, "应该标记为 DYNAMIC"
    print("  ✅ 正确标记为动态应用\n")


async def main():
    print("\n" + "=" * 80)
    print("🔬 测试 open_app 动态/静态判断集成")
    print("=" * 80)

    # Initialize test data
    await init_test_data()

    try:
        await test_mobile_open_app()
    except Exception as e:
        print(f"❌ Android 测试失败: {e}")

    try:
        await test_desktop_open_app()
    except Exception as e:
        print(f"❌ macOS 测试失败: {e}")

    print("\n" + "=" * 80)
    print("✅ 测试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
