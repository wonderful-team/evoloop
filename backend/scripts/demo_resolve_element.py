import asyncio
import os
import json
import unicodedata
from app.infrastructure.drivers.macos import macos_driver
from app.domain.tools.environment.desktop import desktop_control

def normalize_text(t: str) -> str:
    if not t: return ""
    return unicodedata.normalize('NFC', str(t)).lower().strip().replace(" ", "").replace("\u3000", "")

async def demo_resolve_capabilities():
    print("🚀 --- resolve_element 深度解析与归一化匹配 demo ---")
    
    # 1. 自动识别当前窗口，并进行深度解析
    print("\n[Step 1] 正在提取当前活动窗口的深度无障碍树 (Max Depth: 8)...")
    app_info = macos_driver.get_current_app()
    print(f"   当前应用: {app_info.get('name')} | 窗口: {app_info.get('title')}")
    
    raw_tree = macos_driver.dump_ax_tree()
    elements = json.loads(raw_tree)
    print(f"✅ 提取成功：共发现 {len(elements)} 个 UI 元素")

    # 2. 统计深度统计
    depths = [el.get("path", "").count(">") for el in elements]
    max_d = max(depths) if depths else 0
    deep_elements = [el for el in elements if el.get("path", "").count(">") >= 4]
    
    print(f"📊 性能分析：最深层级为 {max_d} 层 (优化前限制为 2 层)")
    
    if deep_elements:
        print(f"   💡 发现 {len(deep_elements)} 个深度 >= 4 的元素。")
        print(f"   示例深度路径: {deep_elements[0]['path']}")
    else:
        print(f"   💡 当前窗口层级较浅 (Max: {max_d})。")

    # 3. 演示元素名与匹配
    print("\n[Step 2] 元素发现与匹配演示...")
    
    named_elements = [el for el in elements if el.get("name")]
    if named_elements:
        # 显示前 3 个有名字的元素及其深度
        print(f"   找到具有语义名称的元素 ({len(named_elements)}个):")
        for el in named_elements[:3]:
            depth = el.get("path", "").count(">")
            print(f"   - '{el['name']}' ({el['role']}) | 深度: {depth}")
            
        target_el = named_elements[0]
        target_name = target_el['name']
        
        # 测试匹配逻辑
        test_queries = [target_name, target_name.replace(" ", "")]
        for query in test_queries:
            target_norm = normalize_text(query)
            # 简化匹配逻辑模拟
            best = None
            for el in elements:
                el_name = normalize_text(el.get("name", ""))
                if target_norm == el_name or target_norm in el_name:
                    best = el
                    break
            
            if best:
                print(f"   🔍 搜索 '{query}' -> ✅ 匹配到 '{best['name']}' (路径: {best['path']})")
    else:
        print("⚠️ 当前窗口没有带名称的元素。")
        # 显示几个无名元素的路径证明深度
        print("   虽然没有名称，但底层路径依然可解析:")
        for el in elements[:3]:
            print(f"   - {el['path']} ({el['role']})")

    print("\n[提示] 请尝试切换到 Chrome 或系统设置窗口，再次运行此脚本以观察更深层的结构。")

if __name__ == "__main__":
    asyncio.run(demo_resolve_capabilities())
