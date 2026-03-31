#!/usr/bin/env python3
"""
DesktopController 直接并发测试 - 绕过HTTP API直接测试控制器
"""

import asyncio
import time
import statistics
from datetime import datetime
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

async def test_concurrent_actions():
    """测试并发的桌面操作"""
    from app.core.environment.controllers.desktop_controller import DesktopController
    
    print("=" * 60)
    print("DesktopController 直接并发测试")
    print("=" * 60)
    print(f"时间: {datetime.now().isoformat()}\n")
    
    # 测试1: 顺序执行
    print("🐢 测试1: 顺序执行 5 个 get_info")
    start = time.time()
    for i in range(5):
        result = await DesktopController.execute({"action": "get_info"})
        print(f"  请求 {i+1}: {result.get('status', 'unknown')}")
    sequential_time = time.time() - start
    print(f"  总耗时: {sequential_time:.2f}s, 平均: {sequential_time/5:.2f}s\n")
    
    # 测试2: 并发执行
    print("🚀 测试2: 并发执行 5 个 get_info")
    start = time.time()
    tasks = [
        DesktopController.execute({"action": "get_info"})
        for _ in range(5)
    ]
    results = await asyncio.gather(*tasks)
    concurrent_time = time.time() - start
    for i, r in enumerate(results):
        print(f"  请求 {i+1}: {r.get('status', 'unknown')}")
    print(f"  总耗时: {concurrent_time:.2f}s, 平均: {concurrent_time/5:.2f}s")
    print(f"  并发加速比: {sequential_time/concurrent_time:.2f}x\n")
    
    # 测试3: 更高并发
    print("🚀 测试3: 并发执行 10 个 list_apps")
    start = time.time()
    tasks = [
        DesktopController.execute({"action": "list_apps"})
        for _ in range(10)
    ]
    results = await asyncio.gather(*tasks)
    concurrent_time = time.time() - start
    success = sum(1 for r in results if r.get('status') == 'success')
    print(f"  成功: {success}/10")
    print(f"  总耗时: {concurrent_time:.2f}s, 平均: {concurrent_time/10:.2f}s\n")
    
    # 测试4: 截图并发测试
    print("📸 测试4: 并发执行 5 个 screenshot")
    start = time.time()
    tasks = [
        DesktopController.execute({"action": "screenshot"})
        for _ in range(5)
    ]
    results = await asyncio.gather(*tasks)
    concurrent_time = time.time() - start
    success = sum(1 for r in results if r.get('status') == 'success')
    print(f"  成功: {success}/5")
    print(f"  总耗时: {concurrent_time:.2f}s, 平均: {concurrent_time/5:.2f}s\n")
    
    # 测试5: 混合操作并发
    print("🔄 测试5: 混合操作并发 (get_info, list_apps, screenshot)")
    actions = ["get_info", "list_apps", "screenshot"] * 3
    start = time.time()
    tasks = [
        DesktopController.execute({"action": action})
        for action in actions
    ]
    results = await asyncio.gather(*tasks)
    concurrent_time = time.time() - start
    success = sum(1 for r in results if r.get('status') == 'success')
    print(f"  成功: {success}/{len(actions)}")
    print(f"  总耗时: {concurrent_time:.2f}s, 平均: {concurrent_time/len(actions):.2f}s\n")
    
    print("=" * 60)
    print("✅ 测试完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_concurrent_actions())
