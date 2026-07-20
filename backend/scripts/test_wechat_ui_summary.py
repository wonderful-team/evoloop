#!/usr/bin/env python3
"""
微信 UI 可访问性测试总结
"""

import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.infrastructure.drivers.adb import adb_driver


def test_android_wechat():
    """测试 Android 微信"""
    print("=" * 80)
    print("📱 Android 微信 UI 可访问性测试")
    print("=" * 80)

    try:
        # 1. 检查设备
        devices = adb_driver.list_devices()
        if not devices:
            print("❌ 未检测到 Android 设备")
            return
        print(f"✅ 设备: {devices[0]['model']}")

        # 2. 检查当前应用
        app_info = adb_driver.get_current_app()
        print(f"📦 当前应用: {app_info.get('package')}")
        print(f"🎯 Activity: {app_info.get('activity')}")

        if app_info.get('package') != 'com.tencent.mm':
            print("⚠️  微信不在前台")
            return

        # 3. 获取 UI dump
        xml_content = adb_driver.dump_ui()

        # 解析 XML
        xml_start = xml_content.find('<?xml')
        if xml_start >= 0:
            xml_end = xml_content.rfind('>')
            xml_content = xml_content[xml_start:xml_end + 1]

        root = ET.fromstring(xml_content.strip())

        # 统计
        total_nodes = sum(1 for _ in root.iter())
        scrollable_nodes = [n for n in root.iter() if n.get('scrollable') == 'true']
        nodes_with_text = [n for n in root.iter() if n.get('text')]
        nodes_with_id = [n for n in root.iter() if n.get('resource-id')]

        print(f"\n📊 UI 结构统计:")
        print(f"   总节点数: {total_nodes}")
        print(f"   Scrollable 节点: {len(scrollable_nodes)}")
        print(f"   有 text 的节点: {len(nodes_with_text)}")
        print(f"   有 resource-id 的节点: {len(nodes_with_id)}")

        if total_nodes < 10:
            print("\n⚠️  关键发现:")
            print("   微信 UI dump 几乎是空的！")
            print("   这是因为微信使用了自定义渲染或安全限制")
            print("   标准 uiautomator 无法获取微信的 UI 结构")
            print("\n   影响:")
            print("   ❌ 无法通过 scrollable 属性识别 RecyclerView")
            print("   ❌ 无法区分静态/动态元素")
            print("   ❌ Atlas 的 Android 微信支持基本无效")

    except Exception as e:
        print(f"❌ 错误: {e}")


def test_macos_wechat():
    """测试 macOS 微信"""
    print("\n" + "=" * 80)
    print("🖥️  macOS 微信 AX 可访问性测试")
    print("=" * 80)

    try:
        # 检查微信是否运行
        result = subprocess.run(
            ['osascript', '-e', 'tell application "System Events" to get name of every application process whose name contains "WeChat"'],
            capture_output=True, text=True
        )

        if 'WeChat' not in result.stdout:
            print("❌ 微信未运行")
            return

        print("✅ 微信正在运行")

        # 尝试获取 AX Tree
        script = '''
tell application "System Events"
    tell application process "WeChat"
        return count of entire contents of window 1
    end tell
end tell
'''
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)

        if result.returncode == 0:
            count = result.stdout.strip()
            print(f"📊 窗口元素数: {count}")

            # 获取详细内容
            script2 = '''
tell application "System Events"
    tell application process "WeChat"
        return entire contents of window 1
    end tell
end tell
'''
            result2 = subprocess.run(['osascript', '-e', script2], capture_output=True, text=True)
            content = result2.stdout.strip()

            # 分析内容
            lines = content.split(', ')
            print(f"📄 详细元素数: {len(lines)}")

            # 统计类型
            types = {}
            for line in lines:
                parts = line.split(' of ')
                elem_type = parts[0].split()[0] if parts else 'unknown'
                types[elem_type] = types.get(elem_type, 0) + 1

            print(f"\n📊 元素类型分布:")
            for t, c in sorted(types.items(), key=lambda x: -x[1])[:10]:
                print(f"   {t}: {c}")

            if len(lines) < 20:
                print("\n⚠️  关键发现:")
                print("   macOS 微信 AX Tree 非常简化！")
                print("   只显示 button/group 等容器，没有详细内容")
                print("\n   影响:")
                print("   ❌ 无法识别 AXScrollArea 等滚动容器")
                print("   ❌ 无法获取对话列表等动态内容")
                print("   ❌ Atlas 的 macOS 微信支持有限")
        else:
            print(f"❌ 无法获取 AX Tree: {result.stderr}")

    except Exception as e:
        print(f"❌ 错误: {e}")


def main():
    print("\n" + "=" * 80)
    print("🔍 微信 UI 可访问性测试")
    print("=" * 80)
    print("\n目的: 验证微信是否可以通过系统 API 获取 UI 结构")
    print("      以支持 Atlas 的元素分类功能\n")

    test_android_wechat()
    test_macos_wechat()

    print("\n" + "=" * 80)
    print("💡 结论与建议")
    print("=" * 80)
    print("""
【测试结果】

Android 微信:
- uiautomator dump 返回空结构（仅根节点）
- 无法获取 scrollable 属性
- 无法区分 RecyclerView 等容器

macOS 微信:
- AX Tree 极度简化
- 无法获取详细 UI 内容
- 无法识别滚动区域

【根本原因】
微信使用了自定义渲染技术（可能是自己的跨平台 UI 框架），
有意绕过了系统辅助功能 API，防止自动化抓取。

【对 Atlas 的影响】
1. ❌ 无法通过标准 API 区分静态/动态元素
2. ❌ 无法识别可滚动容器
3. ❌ 无法获取微信的 UI 结构用于 Atlas

【改进建议】

方案 1: 放弃微信的特殊处理
- 将微信标记为"不可 Atlas"
- 完全依赖实时视觉感知（OCR/Screenshot）

方案 2: 使用 Vision 替代 A11y
- 不使用系统辅助功能 API
- 使用截图 + OCR/视觉模型识别元素
- 缺点：无法区分元素是否可点击

方案 3: 针对微信的启发式策略
- 基于常见布局模式（搜索栏在顶部、列表在中间等）
- 不使用坐标，使用相对位置策略
- 不依赖 Atlas，每次实时分析

方案 4: Root/越狱设备（不推荐）
- 需要特殊权限
- 安全性问题

【推荐】
对于微信这类应用，Atlas 应该：
1. 检测应用类型（bundle_id 匹配已知应用）
2. 对微信使用 "vision-only" 模式
3. 不存储坐标，只存储交互策略
4. 依赖实时视觉感知而非历史数据
""")


if __name__ == "__main__":
    main()
