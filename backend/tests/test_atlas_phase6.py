#!/usr/bin/env python3
"""
Atlas Phase 6 功能验证脚本

测试内容：
1. 动态应用检测
2. 元素分类
3. 策略存储与查询
"""

import asyncio
import sys

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.core.atlas import atlas_engine
from app.core.atlas.models import AtlasApp, AtlasElement, AtlasState
from app.core.atlas.strategy import (
    AppStrategy, AtlasStrategyStore, InteractionStrategy, init_default_strategies
)
from app.core.environment.explorers.dynamic_apps import DynamicAppTriage


async def test_dynamic_app_detection():
    """测试动态应用检测"""
    print("\n" + "="*60)
    print("📱 测试动态应用检测")
    print("="*60)

    # 测试已知的动态应用
    test_apps = [
        "com.tencent.mm",           # Android 微信
        "com.tencent.xinWeChat",    # macOS 微信
        "com.microsoft.Teams",      # Teams
        "com.unknown.app",          # 未知应用
    ]

    dynamic_apps = await DynamicAppTriage.get_dynamic_apps("android")
    print(f"\n动态应用列表 ({len(dynamic_apps)} 个):")
    for app in list(dynamic_apps)[:10]:
        print(f"  • {app}")

    print("\n测试结果:")
    for app in test_apps:
        is_dynamic = app in dynamic_apps
        icon = "✅" if is_dynamic else "❌"
        print(f"  {icon} {app}: {'动态' if is_dynamic else '静态'}")


async def test_element_classification():
    """测试元素分类"""
    print("\n" + "="*60)
    print("🎯 测试元素分类")
    print("="*60)

    # 模拟 Android 微信元素
    test_elements = [
        # RecyclerView (容器)
        AtlasElement(
            role="container",
            label="",
            os_identifier="com.tencent.mm:id/conversation_list",
            bounds={"x": 0, "y": 200, "width": 1080, "height": 1600},
            metadata={"class": "androidx.recyclerview.widget.RecyclerView", "scrollable": True}
        ),
        # 搜索栏 (静态)
        AtlasElement(
            role="input",
            label="搜索",
            os_identifier="com.tencent.mm:id/search_bar",
            bounds={"x": 100, "y": 50, "width": 800, "height": 100},
            metadata={"class": "android.widget.EditText", "scrollable": False}
        ),
        # Alice 对话 (动态)
        AtlasElement(
            role="button",
            label="Alice",
            os_identifier="",
            bounds={"x": 100, "y": 300, "width": 900, "height": 150},
            metadata={"class": "android.widget.LinearLayout", "scrollable": False}
        ),
    ]

    print("\n元素分类结果:")
    for elem in test_elements:
        category = atlas_engine._classify_element_category(elem, "android")
        elem.element_category = category
        elem.is_infrastructure = category in ["static", "static_navigation", "static_toolbar"]
        elem.coordinate_confidence = 0.9 if elem.is_infrastructure else 0.0

        icon = "📍" if elem.is_infrastructure else "📄"
        print(f"  {icon} [{category:20s}] {elem.label or '(no label)':15s} (confidence: {elem.coordinate_confidence})")


async def test_strategy_storage():
    """测试策略存储"""
    print("\n" + "="*60)
    print("💾 测试策略存储")
    print("="*60)

    # 初始化默认策略
    await init_default_strategies()
    print("✅ 初始化默认策略完成")

    # 测试获取微信策略
    strategy = await AtlasStrategyStore.get_strategy("com.tencent.mm")
    if strategy:
        print(f"\n📱 微信 (Android) 策略:")
        print(f"  基础设施元素: {len(strategy.infrastructure)}")
        for infra in strategy.infrastructure:
            print(f"    • {infra.get('role')}: {infra.get('label')}")

        print(f"\n  交互策略: {len(strategy.strategies)}")
        for strat in strategy.strategies:
            print(f"    • {strat.strategy_type}: {strat.target_element}")

        print(f"\n  提示: {strategy.hints}")
    else:
        print("❌ 未找到微信策略")

    # 测试自定义策略
    custom_strategy = AppStrategy(
        bundle_id="com.example.test",
        platform="android",
        infrastructure=[
            {"role": "toolbar", "label": "导航栏", "resource_id": "com.example:id/toolbar"},
        ],
        strategies=[
            InteractionStrategy(
                strategy_type="search_then_click",
                target_element="find_item",
                parameters={"search_bar": "com.example:id/search"}
            )
        ],
        hints={"coordinate_unstable": True}
    )

    await AtlasStrategyStore.save_strategy(custom_strategy)
    print("\n✅ 保存自定义策略")

    retrieved = await AtlasStrategyStore.get_strategy("com.example.test")
    if retrieved:
        print(f"✅ 检索自定义策略成功: {retrieved.bundle_id}")


async def test_atlas_engine_integration():
    """测试 AtlasEngine 集成"""
    print("\n" + "="*60)
    print("🔧 测试 AtlasEngine 集成")
    print("="*60)

    # 测试动态应用检测
    is_dynamic = await atlas_engine.is_dynamic_app("com.tencent.mm", "android")
    print(f"✅ is_dynamic_app('com.tencent.mm'): {is_dynamic}")

    # 测试获取策略
    strategy = await atlas_engine.get_app_strategy("com.tencent.mm", "android")
    if strategy:
        print(f"✅ get_app_strategy('com.tencent.mm'): 成功")
    else:
        print("⚠️ get_app_strategy('com.tencent.mm'): 无策略")


async def main():
    print("\n" + "="*60)
    print("🔍 Atlas Phase 6 功能验证")
    print("="*60)

    try:
        await test_dynamic_app_detection()
        await test_element_classification()
        await test_strategy_storage()
        await test_atlas_engine_integration()

        print("\n" + "="*60)
        print("✅ 所有测试完成")
        print("="*60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
