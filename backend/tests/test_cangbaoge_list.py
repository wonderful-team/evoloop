#!/usr/bin/env python3
"""
测试脚本：获取藏宝阁APP角色列表的UI dump并解析列表项坐标

使用方法：
1. 确保手机连接并开启了藏宝阁APP的角色列表页面
2. 运行: python test_cangbaoge_list.py
"""

import asyncio
import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Optional, Tuple

# 设置路径
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.infrastructure.drivers.adb import adb_driver


def parse_bounds(bounds_str: str) -> Tuple[int, int, int, int]:
    """解析 bounds 字符串 [x1,y1][x2,y2] -> (x1, y1, x2, y2)"""
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
    if match:
        return tuple(map(int, match.groups()))
    return (0, 0, 0, 0)


def is_list_item(node: ET.Element) -> bool:
    """
    判断一个节点是否可能是列表项
    基于类名、可点击性、尺寸等特征
    """
    class_name = node.get("class", "").lower()
    clickable = node.get("clickable") == "true"
    bounds_str = node.get("bounds", "")
    bounds = parse_bounds(bounds_str)

    x1, y1, x2, y2 = bounds
    width = x2 - x1
    height = y2 - y1
    center_y = (y1 + y2) // 2

    # 列表项特征判断
    is_recycler_item = "recyclerview" in class_name or "listview" in class_name
    is_clickable_container = clickable and "layout" in class_name
    has_reasonable_size = 100 < width < 1200 and 80 < height < 500
    is_on_screen = 200 < center_y < 2200  # 排除状态栏和导航栏

    # 文字特征
    text = node.get("text", "") or node.get("content-desc", "")
    has_content = len(text) > 0

    return (is_recycler_item or is_clickable_container) and has_reasonable_size and is_on_screen


def extract_list_items(xml_content: str) -> List[Dict]:
    """
    从UI dump XML中提取列表项

    返回每个列表项的:
    - bounds: 边界坐标 (x1, y1, x2, y2)
    - center: 中心点坐标 (x, y) - 用于点击
    - text: 文本内容
    - class: 类名
    - resource_id: 资源ID
    """
    if not xml_content or not xml_content.strip():
        return []

    # 清理XML：找到XML开始位置
    xml_start = xml_content.find("<?xml")
    if xml_start == -1:
        xml_start = xml_content.find("<hierarchy")

    if xml_start == -1:
        print("错误: 无法找到XML内容")
        return []

    xml_content = xml_content[xml_start:]

    # 清理XML：找到hierarchy结束标签后的内容并截断
    # uiautomator dump 可能在后面添加额外文本如 "UI hierchary dumped to: /dev/tty"
    hierarchy_end = xml_content.rfind("</hierarchy>")
    if hierarchy_end != -1:
        xml_content = xml_content[:hierarchy_end + len("</hierarchy>")]

    # 处理可能的编码问题：移除无效字符
    xml_content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', xml_content)

    try:
        root = ET.fromstring(xml_content.strip())
    except ET.ParseError as e:
        print(f"XML解析错误: {e}")
        return []

    items = []
    seen_bounds = set()  # 去重

    for node in root.iter():
        # 获取节点信息
        class_name = node.get("class", "")
        text = node.get("text", "")
        content_desc = node.get("content-desc", "")
        resource_id = node.get("resource-id", "")
        bounds_str = node.get("bounds", "")
        clickable = node.get("clickable") == "true"
        scrollable = node.get("scrollable") == "true"

        if not bounds_str:
            continue

        bounds = parse_bounds(bounds_str)
        x1, y1, x2, y2 = bounds
        width = x2 - x1
        height = y2 - y1
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2

        # 基础过滤：太小的元素不要
        if width < 50 or height < 50:
            continue

        # 屏幕范围过滤（排除状态栏、导航栏）
        if center_y < 150 or center_y > 2300:
            continue

        # 去重：相同坐标的只保留一个
        bound_key = (x1, y1, x2, y2)
        if bound_key in seen_bounds:
            continue
        seen_bounds.add(bound_key)

        # 判断是否为列表项（多种策略）
        is_list_like = False
        list_indicators = []

        # 策略1: 类名包含列表相关关键词
        if any(kw in class_name.lower() for kw in [
            "recyclerview", "listview", "scrollview",
            "linearlayout", "relativelayout", "framelayout"
        ]):
            is_list_like = True
            list_indicators.append("class_name")

        # 策略2: 可点击且有内容
        if clickable and (text or content_desc):
            is_list_like = True
            list_indicators.append("clickable_with_content")

        # 策略3: 合理的列表项尺寸 (宽度占满屏幕大部分，高度适中)
        if width > 800 and 100 < height < 400:
            is_list_like = True
            list_indicators.append("list_item_size")

        # 策略4: 有resource-id且包含列表相关关键词
        if any(kw in resource_id.lower() for kw in [
            "item", "cell", "row", "card", "product", "role", "character"
        ]):
            is_list_like = True
            list_indicators.append("resource_id")

        item_info = {
            "bounds": bounds,
            "center": (center_x, center_y),
            "text": text[:50] if text else "",
            "content_desc": content_desc[:50] if content_desc else "",
            "class": class_name.split(".")[-1] if "." in class_name else class_name,
            "resource_id": resource_id.split("/")[-1] if "/" in resource_id else resource_id,
            "clickable": clickable,
            "scrollable": scrollable,
            "size": (width, height),
            "is_list_item": is_list_like,
            "indicators": list_indicators
        }

        items.append(item_info)

    # 按Y坐标排序（从上到下）
    items.sort(key=lambda x: x["center"][1])

    return items


def analyze_list_structure(items: List[Dict]) -> Dict:
    """
    分析列表结构，识别可能的列表项组
    """
    if not items:
        return {
            "error": "没有检测到任何元素",
            "total_elements": 0,
            "y_range": (0, 0),
            "avg_height": 0,
            "detected_rows": 0,
            "list_rows": [],
            "potential_list_items": []
        }

    # 计算Y坐标分布
    y_positions = [item["center"][1] for item in items]
    heights = [item["size"][1] for item in items]

    # 找出Y坐标相近的元素组（可能是同一行的列表项）
    y_groups = {}
    for item in items:
        y = item["center"][1]
        # 四舍五入到最近的50像素分组
        y_key = (y // 50) * 50
        if y_key not in y_groups:
            y_groups[y_key] = []
        y_groups[y_key].append(item)

    # 分析哪些分组可能是列表项
    list_rows = []
    for y_key, group in sorted(y_groups.items()):
        # 列表行的特征：高度相似，间距均匀
        if len(group) <= 3:  # 通常一行最多2-3个卡片
            avg_height = sum(item["size"][1] for item in group) / len(group)
            if 80 < avg_height < 600:  # 合理的高度范围
                list_rows.append({
                    "y_center": y_key,
                    "items": group,
                    "count": len(group)
                })

    return {
        "total_elements": len(items),
        "y_range": (min(y_positions), max(y_positions)) if y_positions else (0, 0),
        "avg_height": sum(heights) / len(heights) if heights else 0,
        "detected_rows": len(list_rows),
        "list_rows": list_rows[:10],  # 只显示前10行
        "potential_list_items": [item for item in items if item["is_list_item"]][:15]
    }


async def test_dump_cangbaoge():
    """测试获取藏宝阁APP的UI dump"""

    print("=" * 60)
    print("藏宝阁APP角色列表 UI Dump 测试")
    print("=" * 60)

    # 1. 检查设备连接
    print("\n[1] 检查设备连接...")
    try:
        devices = adb_driver.list_devices()
        if not devices:
            print("❌ 错误: 没有检测到连接的设备")
            return

        print(f"✓ 检测到 {len(devices)} 个设备:")
        for d in devices:
            print(f"   - {d['serial']} ({d['status']})")

        device_id = devices[0]['serial']
    except Exception as e:
        print(f"❌ 设备检查失败: {e}")
        return

    # 2. 获取当前前台应用
    print("\n[2] 获取当前前台应用...")
    try:
        # 尝试获取当前应用
        result = adb_driver.shell("dumpsys window | grep mCurrentFocus", device_id=device_id)
        print(f"   当前焦点窗口: {result}")
    except Exception as e:
        print(f"   获取前台应用失败: {e}")

    # 3. dump UI
    print("\n[3] 执行 UI dump...")
    try:
        xml_content = adb_driver.dump_ui(device_id=device_id)
        print(f"✓ 成功获取 UI dump, 长度: {len(xml_content)} 字符")

        # 保存原始XML以便检查
        with open("/tmp/cangbaoge_dump.xml", "w", encoding="utf-8") as f:
            f.write(xml_content)
        print(f"   原始XML已保存到: /tmp/cangbaoge_dump.xml")

    except Exception as e:
        print(f"❌ UI dump 失败: {e}")
        return

    # 4. 解析列表项
    print("\n[4] 解析列表项...")
    items = extract_list_items(xml_content)
    print(f"✓ 共解析出 {len(items)} 个可见元素")

    # 5. 分析结构
    print("\n[5] 分析列表结构...")
    analysis = analyze_list_structure(items)

    print(f"   总元素数: {analysis['total_elements']}")
    print(f"   Y坐标范围: {analysis['y_range']}")
    print(f"   平均高度: {analysis['avg_height']:.1f}px")
    print(f"   检测到的行数: {analysis['detected_rows']}")

    # 6. 显示检测到的行
    if analysis['detected_rows'] > 0:
        print("\n[6] 检测到的列表行（前10行）:")
        for i, row in enumerate(analysis['list_rows'], 1):
            print(f"\n   第 {i} 行 (Y≈{row['y_center']}):")
            for item in row['items']:
                res_id = item['resource_id'][:30] if item['resource_id'] else "N/A"
                text = item['text'][:20] if item['text'] else ""
                print(f"      → 点击坐标: ({item['center'][0]}, {item['center'][1]})")
                print(f"        尺寸: {item['size']}, 资源ID: {res_id}")
                if text:
                    print(f"        文字: {text}")

    # 7. 显示可能的列表项
    potential = analysis['potential_list_items']
    if potential:
        print(f"\n[7] 可能的列表项（前{len(potential)}个）:")
        for i, item in enumerate(potential, 1):
            print(f"\n   {i}. 坐标: ({item['center'][0]}, {item['center'][1]})")
            print(f"      范围: {item['bounds']}")
            print(f"      类名: {item['class']}")
            print(f"      资源ID: {item['resource_id']}")
            print(f"      可点击: {item['clickable']}")
            print(f"      判断依据: {', '.join(item['indicators'])}")
            if item['text']:
                print(f"      文字: {item['text']}")
            if item['content_desc']:
                print(f"      描述: {item['content_desc']}")

    # 8. 生成可执行的点击脚本
    print("\n[8] 生成的点击序列（用于遍历列表）:")
    clickable_items = [item for item in items if item['clickable'] and item['is_list_item']]
    if len(clickable_items) >= 2:
        # 计算平均行高
        y_positions = sorted([item['center'][1] for item in clickable_items])
        if len(y_positions) >= 2:
            avg_row_height = sum(y_positions[i+1] - y_positions[i] for i in range(len(y_positions)-1)) / (len(y_positions)-1)
        else:
            avg_row_height = 200

        print(f"   检测到的平均行高: {avg_row_height:.0f}px")
        print("\n   建议的点击序列:")
        for i, item in enumerate(clickable_items[:5], 1):
            print(f"      {i}. tap {item['center'][0]} {item['center'][1]}  # {item['text'][:15] if item['text'] else '无文字'}")

        print(f"\n   滑动到下一页的坐标增量: ~{avg_row_height:.0f}px")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

    return items


if __name__ == "__main__":
    asyncio.run(test_dump_cangbaoge())
