#!/usr/bin/env python3
"""
专门提取藏宝阁APP角色卡片的坐标

基于测试结果，角色卡片特征：
- 尺寸：宽度~1080，高度~200-250px
- 包含价格文本（￥开头）
- Y坐标范围：约550-2100
"""

import asyncio
import re
from typing import Dict, List, Tuple

import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.infrastructure.drivers.adb import adb_driver


def parse_bounds(bounds_str: str) -> Tuple[int, int, int, int]:
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
    if match:
        return tuple(map(int, match.groups()))
    return (0, 0, 0, 0)


def is_price_text(text: str) -> bool:
    """判断是否为价格文本"""
    return text and ('￥' in text or '¥' in text or '元' in text) and any(c.isdigit() for c in text)


def extract_role_cards(xml_content: str) -> List[Dict]:
    """提取角色卡片列表项"""
    import xml.etree.ElementTree as ET

    if not xml_content:
        return []

    # 清理XML
    xml_start = xml_content.find("<?xml")
    if xml_start == -1:
        xml_start = xml_content.find("<hierarchy")
    if xml_start == -1:
        return []

    xml_content = xml_content[xml_start:]
    hierarchy_end = xml_content.rfind("</hierarchy>")
    if hierarchy_end != -1:
        xml_content = xml_content[:hierarchy_end + len("</hierarchy>")]

    xml_content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', xml_content)

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"XML解析错误: {e}")
        return []

    # 第一遍：收集所有价格节点的Y坐标
    price_y_positions = set()
    for node in root.iter():
        text = node.get("text", "")
        if is_price_text(text):
            bounds = parse_bounds(node.get("bounds", ""))
            if bounds != (0, 0, 0, 0):
                center_y = (bounds[1] + bounds[3]) // 2
                price_y_positions.add(center_y)

    print(f"  检测到 {len(price_y_positions)} 个价格标签")

    # 第二遍：找包含价格的大容器（角色卡片）
    cards = []
    seen_cards = set()

    for node in root.iter():
        bounds_str = node.get("bounds", "")
        bounds = parse_bounds(bounds_str)
        x1, y1, x2, y2 = bounds

        width = x2 - x1
        height = y2 - y1
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2

        # 角色卡片特征判断
        is_wide_container = width > 800 and 150 < height < 400
        has_price_nearby = any(abs(center_y - py) < 100 for py in price_y_positions)
        is_on_screen = 400 < center_y < 2100
        is_not_nav_bar = y1 > 100 and y2 < 2200

        if is_wide_container and has_price_nearby and is_on_screen and is_not_nav_bar:
            # 去重
            card_key = (x1, y1, x2, y2)
            if card_key in seen_cards:
                continue
            seen_cards.add(card_key)

            # 提取卡片内的详细信息
            card_info = {
                "bounds": bounds,
                "center": (center_x, center_y),
                "size": (width, height),
                "class": node.get("class", "").split(".")[-1],
                "clickable": node.get("clickable") == "true",
                "children": []
            }

            cards.append(card_info)

    # 按Y坐标排序
    cards.sort(key=lambda x: x["center"][1])
    return cards


def estimate_scroll_distance(cards: List[Dict]) -> int:
    """估算滑动距离"""
    if len(cards) < 2:
        return 250  # 默认值

    y_positions = [c["center"][1] for c in cards]
    distances = [y_positions[i+1] - y_positions[i] for i in range(len(y_positions)-1)]

    # 过滤异常值（只保留100-500之间的）
    valid_distances = [d for d in distances if 100 < d < 500]

    if valid_distances:
        return int(sum(valid_distances) / len(valid_distances))
    return 250


async def main():
    print("=" * 60)
    print("藏宝阁APP - 角色卡片坐标提取")
    print("=" * 60)

    # 获取UI dump
    print("\n[1] 获取UI dump...")
    try:
        xml_content = adb_driver.dump_ui()
        print(f"   ✓ 成功获取，长度: {len(xml_content)} 字符")
    except Exception as e:
        print(f"   ✗ 失败: {e}")
        return

    # 提取角色卡片
    print("\n[2] 提取角色卡片...")
    cards = extract_role_cards(xml_content)

    if not cards:
        print("   ✗ 未检测到角色卡片")
        return

    print(f"   ✓ 检测到 {len(cards)} 个角色卡片:\n")

    for i, card in enumerate(cards, 1):
        print(f"   卡片 {i}:")
        print(f"      点击坐标: ({card['center'][0]}, {card['center'][1]})")
        print(f"      范围: {card['bounds']}")
        print(f"      尺寸: {card['size']}")
        print(f"      可点击: {card['clickable']}")
        print()

    # 计算滑动距离
    scroll_dist = estimate_scroll_distance(cards)
    print(f"[3] 建议的滑动距离: ~{scroll_dist}px")

    # 生成采集宏逻辑
    print("\n[4] 遍历采集策略:")
    print("   " + "-" * 50)
    print("   对于每个角色卡片:")
    print("      1. 点击卡片中心 (x, y)")
    print("      2. 等待详情页加载")
    print("      3. 提取详情数据")
    print("      4. 返回列表")
    print("      5. 向下滑动 {}px".format(scroll_dist))
    print("   " + "-" * 50)

    # 生成具体坐标代码
    print("\n[5] 生成的采集代码:")
    print("   ```python")
    print("   # 当前屏幕可见的角色卡片坐标")
    print("   role_cards = [")
    for card in cards:
        print(f"       {{'x': {card['center'][0]}, 'y': {card['center'][1]}}},  # 范围: {card['bounds']}")
    print("   ]")
    print()
    print(f"   # 滑动距离: {scroll_dist}px")
    print("   ```")

    # 问题提示
    print("\n[6] ⚠️ 重要提示:")
    print("   - 点击返回后列表会回到顶部")
    print("   - 需要记录已采集的项，避免重复")
    print("   - 建议策略: 每次从顶部开始，按顺序点击")
    print("   - 或使用OCR识别价格去重")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
