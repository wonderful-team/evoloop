#!/usr/bin/env python3
"""
两步采集方案验证：
阶段1：遍历列表页，收集每个角色的唯一标识（价格+特征）
阶段2：统一采集详情页

优势：
- 避免列表/详情来回切换的性能损耗
- 支持断点续传（列表采完即使中断也不丢进度）
- 可并行采集详情（多设备）
"""

import xml.etree.ElementTree as ET
import re
import json
import os
from typing import Dict, List, Tuple
from datetime import datetime

import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.infrastructure.drivers.adb import adb_driver


def parse_bounds(bounds_str: str) -> Tuple[int, int, int, int]:
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
    if match:
        return tuple(map(int, match.groups()))
    return (0, 0, 0, 0)


def is_price_text(text: str) -> bool:
    return text and ('￥' in text or '¥' in text) and any(c.isdigit() for c in text)


def parse_ui_dump(xml_content: str) -> List[Dict]:
    """解析UI dump，提取所有可见元素"""
    if not xml_content:
        return []

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
    except ET.ParseError:
        return []

    elements = []
    for node in root.iter():
        text = node.get("text", "")
        bounds = parse_bounds(node.get("bounds", ""))
        if bounds == (0, 0, 0, 0):
            continue

        elements.append({
            'text': text,
            'content_desc': node.get("content-desc", ""),
            'resource_id': node.get("resource-id", ""),
            'class': node.get("class", "").split(".")[-1],
            'bounds': bounds,
            'center_x': (bounds[0] + bounds[2]) // 2,
            'center_y': (bounds[1] + bounds[3]) // 2,
            'clickable': node.get("clickable") == "true"
        })

    return elements


def extract_role_cards_from_list(elements: List[Dict]) -> List[Dict]:
    """
    从列表页元素中提取角色卡片信息
    不点击，仅通过视觉特征识别
    """
    # 找到所有价格标签
    price_elements = [e for e in elements if is_price_text(e['text'])]
    price_elements.sort(key=lambda x: x['center_y'])

    cards = []
    for price_elem in price_elements:
        price_y = price_elem['center_y']

        # 在同一水平线附近找其他信息（上方150px范围内）
        nearby_elements = [
            e for e in elements
            if abs(e['center_y'] - price_y) < 150
            and e['center_y'] < price_y  # 在价格上方
            and e['text']  # 有文字
            and not is_price_text(e['text'])  # 不是价格
        ]

        # 提取角色特征
        role_info = {
            'price': price_elem['text'],
            'price_y': price_y,
            'tap_x': 540,  # 屏幕中央
            'tap_y': price_y - 50,  # 点击价格上方一点（卡片中央）
            'nearby_texts': [e['text'] for e in nearby_elements[:3]],
            'signature': None  # 唯一标识，稍后计算
        }

        # 生成唯一标识：价格+附近文本的组合
        sig_parts = [role_info['price']] + role_info['nearby_texts']
        role_info['signature'] = "|".join(sig_parts)[:100]

        cards.append(role_info)

    return cards


def simulate_collect_list_phase(max_batches: int = 3) -> List[Dict]:
    """
    模拟阶段1：采集列表页
    实际应该循环滑动收集，这里先做单屏测试
    """
    print(f"\n[阶段1] 开始采集列表页（计划{max_batches}屏）...")

    all_cards = []
    seen_signatures = set()

    for batch in range(max_batches):
        print(f"\n  采集第 {batch + 1} 屏...")

        # 获取UI dump
        try:
            xml_content = adb_driver.dump_ui()
        except Exception as e:
            print(f"    ✗ dump失败: {e}")
            continue

        elements = parse_ui_dump(xml_content)
        cards = extract_role_cards_from_list(elements)

        new_count = 0
        for card in cards:
            if card['signature'] not in seen_signatures:
                seen_signatures.add(card['signature'])
                card['batch'] = batch + 1
                card['collected_at'] = datetime.now().isoformat()
                all_cards.append(card)
                new_count += 1

        print(f"    ✓ 本屏发现 {len(cards)} 个，新增 {new_count} 个")

        if batch < max_batches - 1:
            # 滑动到下一屏
            print(f"    → 滑动到下一屏...")
            try:
                adb_driver.shell("input swipe 540 1800 540 500 300")
                import time
                time.sleep(1.5)  # 等待加载
            except Exception as e:
                print(f"    ✗ 滑动失败: {e}")

    print(f"\n[阶段1完成] 共收集 {len(all_cards)} 个角色卡片")
    return all_cards


def save_collection(cards: List[Dict], filepath: str = "/tmp/cbg_collection.json"):
    """保存采集到的列表信息"""
    data = {
        'app': 'com.netease.cbg',
        'collected_at': datetime.now().isoformat(),
        'total_count': len(cards),
        'cards': cards
    }

    # 如果文件已存在，先读取合并（断点续传）
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
            old_signatures = {c['signature'] for c in old_data.get('cards', [])}
            for card in cards:
                if card['signature'] not in old_signatures:
                    old_data['cards'].append(card)
            old_data['total_count'] = len(old_data['cards'])
            data = old_data
            print(f"  合并已有数据，当前共 {data['total_count']} 条")
        except:
            pass

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  数据已保存到: {filepath}")
    return filepath


def simulate_detail_collection(collection_file: str, limit: int = 5):
    """
    模拟阶段2：采集详情页
    这里只打印要采集的项，不实际执行
    """
    print(f"\n[阶段2] 开始采集详情页...")

    with open(collection_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    cards = data.get('cards', [])
    print(f"  待采集角色数: {len(cards)}")

    # 标记已采集状态（支持断点续传）
    completed = [c for c in cards if c.get('detail_collected')]
    pending = [c for c in cards if not c.get('detail_collected')]

    print(f"  已完成: {len(completed)}, 待采集: {len(pending)}")

    # 采集前limit个
    for i, card in enumerate(pending[:limit], 1):
        print(f"\n  [{i}/{min(limit, len(pending))}] 采集角色:")
        print(f"    签名: {card['signature'][:50]}...")
        print(f"    点击坐标: ({card['tap_x']}, {card['tap_y']})")
        print(f"    预计步骤:")
        print(f"      1. tap {card['tap_x']} {card['tap_y']}")
        print(f"      2. wait 2s")
        print(f"      3. extract detail_data")
        print(f"      4. back")
        print(f"      5. wait 0.5s")

        # 标记为已采集（实际应该在成功采集后标记）
        card['detail_collected'] = True
        card['detail_collected_at'] = datetime.now().isoformat()

    # 保存进度
    with open(collection_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n[阶段2完成] 本次采集 {min(limit, len(pending))} 个角色")
    remaining = len([c for c in cards if not c.get('detail_collected')])
    print(f"  剩余待采集: {remaining}")


def show_collection_stats(collection_file: str):
    """显示采集统计"""
    if not os.path.exists(collection_file):
        print("暂无采集数据")
        return

    with open(collection_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    cards = data.get('cards', [])
    completed = [c for c in cards if c.get('detail_collected')]

    print(f"\n📊 采集统计:")
    print(f"  总收集: {len(cards)} 个角色")
    print(f"  已采集详情: {len(completed)}")
    print(f"  待采集详情: {len(cards) - len(completed)}")
    print(f"  进度: {len(completed)/len(cards)*100:.1f}%" if cards else "  N/A")

    # 显示前5个待采集的
    pending = [c for c in cards if not c.get('detail_collected')][:5]
    if pending:
        print(f"\n  前5个待采集:")
        for i, c in enumerate(pending, 1):
            print(f"    {i}. {c['price']} - {c['nearby_texts'][0] if c['nearby_texts'] else 'N/A'}")


def main():
    print("=" * 70)
    print("藏宝阁APP - 两步采集方案验证")
    print("=" * 70)
    print("""
方案说明:
┌─────────────────────────────────────────────────────────────────┐
│ 阶段1: 列表采集                                                  │
│   ├─ 遍历列表页（多屏滑动）                                       │
│   ├─ 提取每个角色的: 价格 + 可见特征 + 点击坐标                    │
│   ├─ 生成唯一标识（去重）                                         │
│   └─ 保存到本地文件（支持断点续传）                                │
│                                                                  │
│ 阶段2: 详情采集                                                  │
│   ├─ 读取已保存的角色列表                                         │
│   ├─ 遍历点击每个角色进入详情页                                    │
│   ├─ 采集详情数据（支持中断恢复）                                  │
│   └─ 标记已采集状态                                              │
└─────────────────────────────────────────────────────────────────┘
    """)

    collection_file = "/tmp/cbg_collection.json"

    # 检查是否已有数据
    if os.path.exists(collection_file):
        print(f"\n发现已有采集数据: {collection_file}")
        show_collection_stats(collection_file)

        choice = input("\n请选择:\n  1. 继续采集列表（增量）\n  2. 开始采集详情\n  3. 查看统计\n  其他. 退出\n> ").strip()

        if choice == "1":
            cards = simulate_collect_list_phase(max_batches=3)
            if cards:
                save_collection(cards, collection_file)
                show_collection_stats(collection_file)

        elif choice == "2":
            limit = input("采集多少个？（默认5）> ").strip()
            limit = int(limit) if limit.isdigit() else 5
            simulate_detail_collection(collection_file, limit)
            show_collection_stats(collection_file)

        elif choice == "3":
            show_collection_stats(collection_file)

    else:
        print("\n暂无采集数据，开始阶段1采集...")
        cards = simulate_collect_list_phase(max_batches=3)
        if cards:
            save_collection(cards, collection_file)
            show_collection_stats(collection_file)

            proceed = input("\n是否开始阶段2采集详情？（y/n）> ").strip().lower()
            if proceed == 'y':
                limit = input("采集多少个？（默认5）> ").strip()
                limit = int(limit) if limit.isdigit() else 5
                simulate_detail_collection(collection_file, limit)
                show_collection_stats(collection_file)

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
