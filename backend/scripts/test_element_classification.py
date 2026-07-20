#!/usr/bin/env python3
"""
测试脚本：验证 Android 和 macOS 微信 UI 的元素分类可行性

功能：
1. 获取 Android 微信 UI dump，分析 scrollable 容器特征
2. 获取 macOS 微信 AX dump，分析滚动相关属性
3. 输出元素分类建议
"""

import asyncio
import ast
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

# 添加项目路径
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.infrastructure.drivers.adb import adb_driver, ADBError
from app.infrastructure.drivers.macos import macos_driver


@dataclass
class AndroidElement:
    """Android UI 元素"""
    index: str
    text: str
    resource_id: str
    class_name: str
    package: str
    bounds: tuple
    checkable: bool
    checked: bool
    clickable: bool
    enabled: bool
    focusable: bool
    focused: bool
    scrollable: bool
    long_clickable: bool
    password: bool
    selected: bool
    content_desc: str
    # 层级关系
    parent: Optional['AndroidElement'] = None
    children: list = field(default_factory=list)
    depth: int = 0


@dataclass
class MacOSElement:
    """macOS AX 元素"""
    name: str
    role: str
    subrole: str
    path: str
    bounds: list
    parent: Optional['MacOSElement'] = None
    children: list = field(default_factory=list)
    depth: int = 0


def parse_bounds(bounds_str: str) -> tuple:
    """解析 bounds 字符串 [x1,y1][x2,y2]"""
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
    if match:
        return tuple(map(int, match.groups()))
    return (0, 0, 0, 0)


def analyze_android_scrollable(node: ET.Element, depth: int = 0, parent=None) -> list:
    """
    递归分析 Android XML，识别可滚动容器
    """
    elements = []

    # 提取所有属性
    elem = AndroidElement(
        index=node.get("index", ""),
        text=node.get("text", ""),
        resource_id=node.get("resource-id", ""),
        class_name=node.get("class", ""),
        package=node.get("package", ""),
        bounds=parse_bounds(node.get("bounds", "")),
        checkable=node.get("checkable") == "true",
        checked=node.get("checked") == "true",
        clickable=node.get("clickable") == "true",
        enabled=node.get("enabled") == "true",
        focusable=node.get("focusable") == "true",
        focused=node.get("focused") == "true",
        scrollable=node.get("scrollable") == "true",
        long_clickable=node.get("long-clickable") == "true",
        password=node.get("password") == "true",
        selected=node.get("selected") == "true",
        content_desc=node.get("content-desc", ""),
        parent=parent,
        depth=depth
    )

    elements.append(elem)

    # 递归处理子节点
    for child in node:
        child_elems = analyze_android_scrollable(child, depth + 1, elem)
        elem.children.extend(child_elems)
        elements.extend(child_elems)

    return elements


def classify_android_element(elem: AndroidElement) -> str:
    """
    根据特征分类元素
    """
    class_lower = elem.class_name.lower()

    # 1. 识别可滚动容器
    SCROLLABLE_CLASSES = [
        "recyclerview", "listview", "scrollview",
        "viewpager", "horizontalscrollview"
    ]

    if elem.scrollable or any(c in class_lower for c in SCROLLABLE_CLASSES):
        if "recyclerview" in class_lower:
            return "container_recyclerview"
        elif "listview" in class_lower:
            return "container_listview"
        elif "scrollview" in class_lower:
            return "container_scrollview"
        elif "webview" in class_lower:
            return "container_webview"
        return "container_scrollable"

    # 2. 检查是否在可滚动容器内（通过 parent 链）
    parent = elem.parent
    while parent:
        if parent.scrollable:
            # 在滚动容器内的元素
            if "textview" in class_lower or "imageview" in class_lower:
                return "dynamic_content"
            return "dynamic"
        parent = parent.parent

    # 3. 静态交互元素（固定位置的按钮等）
    if elem.clickable or elem.focusable:
        # 检查位置是否在屏幕固定区域
        x1, y1, x2, y2 = elem.bounds
        # 假设标准屏幕高度，顶部导航栏或底部导航栏
        if y2 < 200:  # 顶部导航
            return "static_navigation_top"
        elif y1 > 1800:  # 底部导航
            return "static_navigation_bottom"
        return "static"

    # 4. 纯显示文本
    if elem.text and "textview" in class_lower:
        return "static_text"

    return "unknown"


def analyze_macos_ax_tree(raw_output: str) -> list:
    """
    解析 macOS AX Tree
    """
    elements = []

    try:
        # 清理输出
        cleaned = raw_output.replace("missing value", "None")
        data = ast.literal_eval(cleaned)

        def parse_node(node_data, depth=0, parent=None):
            if not isinstance(node_data, dict):
                return

            elem = MacOSElement(
                name=node_data.get("name", ""),
                role=node_data.get("role", ""),
                subrole=node_data.get("subrole", ""),
                path=node_data.get("path", ""),
                bounds=node_data.get("bounds", []),
                parent=parent,
                depth=depth
            )
            elements.append(elem)

            # 递归处理子节点
            for child in node_data.get("children", []):
                parse_node(child, depth + 1, elem)

        for item in data:
            parse_node(item)

    except Exception as e:
        print(f"解析 macOS AX Tree 失败: {e}")

    return elements


def classify_macos_element(elem: MacOSElement) -> str:
    """
    根据 macOS AX 属性分类元素
    """
    role_lower = elem.role.lower()
    subrole_lower = elem.subrole.lower() if elem.subrole else ""

    # 1. 识别可滚动区域
    if "scroll" in role_lower or "scroll" in subrole_lower:
        return "container_scrollable"

    # 2. 表格/列表视图
    if "table" in role_lower or "outline" in role_lower:
        return "container_table"

    # 3. 列表项
    if "row" in role_lower or "item" in subrole_lower:
        # 检查父元素
        parent = elem.parent
        while parent:
            if "table" in parent.role.lower() or "scroll" in parent.role.lower():
                return "dynamic"
            parent = parent.parent

    # 4. 静态交互元素
    if "button" in role_lower or "menu" in role_lower:
        return "static"

    # 5. 工具栏
    if "toolbar" in role_lower:
        return "static_toolbar"

    return "unknown"


def print_android_analysis(elements: list):
    """
    打印 Android UI 分析结果
    """
    print("\n" + "=" * 80)
    print("📱 Android 微信 UI 分析报告")
    print("=" * 80)

    # 统计各类元素
    categories = {}
    scrollable_containers = []
    static_navigations = []
    dynamic_elements = []

    for elem in elements:
        category = classify_android_element(elem)
        categories[category] = categories.get(category, 0) + 1

        if "container" in category:
            scrollable_containers.append(elem)
        elif "static_navigation" in category:
            static_navigations.append(elem)
        elif category in ["dynamic", "dynamic_content"]:
            dynamic_elements.append(elem)

    # 1. 总体统计
    print("\n📊 元素分类统计:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        icon = {
            "container_recyclerview": "🔄",
            "container_listview": "📜",
            "container_scrollview": "📜",
            "container_webview": "🌐",
            "container_scrollable": "📜",
            "dynamic": "📄",
            "dynamic_content": "📝",
            "static_navigation_top": "🔝",
            "static_navigation_bottom": "🔽",
            "static": "📍",
            "static_text": "📄",
            "unknown": "❓"
        }.get(cat, "•")
        print(f"  {icon} {cat}: {count}")

    # 2. 可滚动容器详情
    print(f"\n🔄 可滚动容器详情 ({len(scrollable_containers)} 个):")
    for container in scrollable_containers[:5]:  # 只显示前5个
        print(f"  • {container.class_name.split('.')[-1]}")
        print(f"    ID: {container.resource_id or 'N/A'}")
        print(f"    Bounds: {container.bounds}")
        print(f"    Scrollable: {container.scrollable}")
        print(f"    Children: {len(container.children)}")

    # 3. 静态导航元素
    print(f"\n🔝 静态导航元素 ({len(static_navigations)} 个):")
    for nav in static_navigations[:10]:
        text = nav.text or nav.content_desc or nav.resource_id.split("/")[-1] if nav.resource_id else "Unknown"
        print(f"  • [{nav.class_name.split('.')[-1]}] {text[:30]}")

    # 4. 动态元素示例
    print(f"\n📄 动态元素示例 ({len(dynamic_elements)} 个，显示前5个):")
    for dyn in dynamic_elements[:5]:
        text = dyn.text or dyn.content_desc or "No text"
        parent_info = ""
        p = dyn.parent
        while p:
            if p.scrollable:
                parent_info = f" (in {p.class_name.split('.')[-1]})"
                break
            p = p.parent
        print(f"  • {text[:30]}{parent_info}")

    # 5. 关键发现
    print("\n💡 关键发现:")
    if scrollable_containers:
        print(f"  ✅ 发现 {len(scrollable_containers)} 个可滚动容器")
        print(f"  ✅ 可以基于 scrollable 属性识别动态内容")
    else:
        print("  ⚠️ 未发现可滚动容器（可能不在列表页面）")

    if static_navigations:
        print(f"  ✅ 发现 {len(static_navigations)} 个静态导航元素，适合 Atlas 记录")


async def test_android_wechat():
    """
    测试 Android 微信 UI
    """
    print("\n" + "=" * 80)
    print("🤖 正在获取 Android 微信 UI 数据...")
    print("=" * 80)

    try:
        # 检查设备连接
        devices = adb_driver.list_devices()
        if not devices:
            print("❌ 未检测到 Android 设备")
            return

        print(f"✅ 检测到设备: {devices[0]['serial']}")

        # 获取当前应用信息
        app_info = adb_driver.get_current_app()
        print(f"📱 当前应用: {app_info.get('package', 'unknown')}")
        print(f"🎯 当前 Activity: {app_info.get('activity', 'unknown')}")

        # 获取 UI dump
        xml_content = adb_driver.dump_ui()

        # 解析 XML
        xml_start = xml_content.find("<?xml")
        if xml_start == -1:
            xml_start = xml_content.find("<hierarchy")

        if xml_start >= 0:
            xml_end = xml_content.rfind(">")
            if xml_end > xml_start:
                xml_content = xml_content[xml_start:xml_end + 1]

        root = ET.fromstring(xml_content.strip())

        # 分析元素
        elements = analyze_android_scrollable(root)

        # 打印分析结果
        print_android_analysis(elements)

        # 输出原始 XML 片段（用于调试）
        print("\n📝 XML 结构片段 (前 2000 字符):")
        print(xml_content[:2000])

    except ADBError as e:
        print(f"❌ ADB 错误: {e}")
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


def print_macos_analysis(elements: list):
    """
    打印 macOS AX 分析结果
    """
    print("\n" + "=" * 80)
    print("🖥️  macOS 微信 AX 分析报告")
    print("=" * 80)

    # 统计
    categories = {}
    scrollable_containers = []
    static_elements = []

    for elem in elements:
        category = classify_macos_element(elem)
        categories[category] = categories.get(category, 0) + 1

        if "container" in category:
            scrollable_containers.append(elem)
        elif "static" in category:
            static_elements.append(elem)

    # 1. 总体统计
    print("\n📊 元素分类统计:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        icon = {
            "container_scrollable": "🔄",
            "container_table": "📊",
            "dynamic": "📄",
            "static_toolbar": "🔧",
            "static": "📍",
            "unknown": "❓"
        }.get(cat, "•")
        print(f"  {icon} {cat}: {count}")

    # 2. 可滚动区域
    print(f"\n🔄 可滚动区域 ({len(scrollable_containers)} 个):")
    for container in scrollable_containers[:5]:
        print(f"  • [{container.role}] {container.name[:30]}")
        print(f"    Subrole: {container.subrole}")
        print(f"    Bounds: {container.bounds}")

    # 3. 静态元素
    print(f"\n📍 静态元素示例 ({len(static_elements)} 个，显示前10个):")
    for elem in static_elements[:10]:
        name = elem.name or "Unnamed"
        print(f"  • [{elem.role}] {name[:40]}")

    # 4. 关键发现
    print("\n💡 关键发现:")
    if scrollable_containers:
        print(f"  ✅ 发现 {len(scrollable_containers)} 个可滚动区域")
    else:
        print("  ⚠️ 未发现可滚动区域（可能 macOS 微信结构不同）")


async def test_macos_wechat():
    """
    测试 macOS 微信 AX
    """
    print("\n" + "=" * 80)
    print("🖥️  正在获取 macOS 微信 AX 数据...")
    print("=" * 80)

    try:
        # 检查辅助功能权限
        if not macos_driver.check_accessibility_permission():
            print("❌ 未授予辅助功能权限")
            print("   请前往 系统设置 > 隐私与安全性 > 辅助功能 添加终端应用")
            return

        # 获取当前应用
        app_info = macos_driver.get_current_app()
        print(f"📱 当前应用: {app_info.get('name', 'unknown')}")
        print(f"📦 Bundle ID: {app_info.get('bundle_id', 'unknown')}")
        print(f"🎯 窗口标题: {app_info.get('title', 'unknown')}")

        # 获取 AX Tree
        raw_output = macos_driver.dump_ax_tree()

        if raw_output.startswith("Error"):
            print(f"❌ 获取 AX Tree 失败: {raw_output}")
            return

        # 解析 AX Tree
        elements = analyze_macos_ax_tree(raw_output)

        # 打印分析结果
        print_macos_analysis(elements)

        # 输出原始数据片段
        print("\n📝 AX Tree 片段 (前 2000 字符):")
        print(raw_output[:2000])

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """
    主函数
    """
    print("\n" + "=" * 80)
    print("🔍 Atlas 元素分类可行性测试")
    print("=" * 80)
    print("\n此脚本将分析 Android 和 macOS 微信的 UI 结构")
    print("验证是否可以基于系统 API 区分静态/动态元素\n")

    # 测试 Android
    await test_android_wechat()

    # 测试 macOS
    await test_macos_wechat()

    print("\n" + "=" * 80)
    print("✅ 测试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
