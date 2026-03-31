#!/usr/bin/env python3
"""
并发测试 - 测试DesktopController的异步性能
"""

import asyncio
import aiohttp
import time
import json
import statistics
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"

# 创建会话ID
session_id = f"concurrent-test-{int(time.time())}"

async def create_session(session):
    """创建测试会话"""
    payload = {
        "title": "并发测试",
        "context": "测试DesktopController异步性能",
        "mode": "standard"
    }
    async with session.post(f"{BASE_URL}/conversations/", json=payload) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data.get("id")
        return None

async def send_desktop_command(session, session_id, action, params=None):
    """发送桌面控制命令"""
    payload = {
        "input": f"测试命令: {action}",
        "context": {
            "session_id": session_id,
            "mode": "batch"
        },
        "override_routing": True,
        "target_worker_type": "desktop",
        "agent_config": {
            "role_name": "Workspace Operator"
        }
    }
    
    start = time.time()
    try:
        async with session.post(
            f"{BASE_URL}/api/v1/chat", 
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            elapsed = time.time() - start
            status = resp.status
            try:
                data = await resp.json()
            except:
                data = {"text": await resp.text()}
            return {
                "action": action,
                "status": status,
                "elapsed": elapsed,
                "success": 200 <= status < 300
            }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "action": action,
            "status": 0,
            "elapsed": elapsed,
            "success": False,
            "error": str(e)
        }

async def test_concurrent_requests(num_concurrent=5, num_requests=20):
    """测试并发请求性能"""
    print(f"\n🚀 开始并发测试: {num_concurrent}并发 x {num_requests}请求")
    print(f"时间: {datetime.now().isoformat()}")
    print("-" * 60)
    
    async with aiohttp.ClientSession() as session:
        # 创建会话
        session_id = await create_session(session)
        if not session_id:
            print("❌ 无法创建会话")
            return
        print(f"✅ 会话创建: {session_id}")
        
        # 准备测试命令
        actions = [
            "get_info",
            "screenshot", 
            "list_apps",
            "get_info",
            "screenshot"
        ] * (num_requests // 5 + 1)
        actions = actions[:num_requests]
        
        # 并发发送请求
        semaphore = asyncio.Semaphore(num_concurrent)
        
        async def bounded_request(action):
            async with semaphore:
                return await send_desktop_command(session, session_id, action)
        
        start_total = time.time()
        tasks = [bounded_request(action) for action in actions]
        results = await asyncio.gather(*tasks)
        total_elapsed = time.time() - start_total
        
        # 统计结果
        success_count = sum(1 for r in results if r["success"])
        fail_count = len(results) - success_count
        latencies = [r["elapsed"] for r in results]
        
        print(f"\n📊 并发测试结果:")
        print(f"  总请求数: {len(results)}")
        print(f"  成功: {success_count}")
        print(f"  失败: {fail_count}")
        print(f"  总耗时: {total_elapsed:.2f}s")
        print(f"  平均延迟: {statistics.mean(latencies):.2f}s")
        print(f"  最小延迟: {min(latencies):.2f}s")
        print(f"  最大延迟: {max(latencies):.2f}s")
        print(f"  中位延迟: {statistics.median(latencies):.2f}s")
        print(f"  吞吐量: {len(results)/total_elapsed:.1f} req/s")
        
        if len(latencies) > 1:
            print(f"  延迟标准差: {statistics.stdev(latencies):.2f}s")
        
        # 显示失败的请求
        failures = [r for r in results if not r["success"]]
        if failures:
            print(f"\n❌ 失败的请求:")
            for f in failures[:5]:
                print(f"  - {f['action']}: {f.get('error', f['status'])}")

async def test_sequential_requests(num_requests=10):
    """测试顺序请求性能(作为对比)"""
    print(f"\n🐢 顺序请求测试: {num_requests}请求")
    print("-" * 60)
    
    async with aiohttp.ClientSession() as session:
        session_id = await create_session(session)
        if not session_id:
            print("❌ 无法创建会话")
            return
        
        actions = ["get_info"] * num_requests
        
        start_total = time.time()
        results = []
        for action in actions:
            result = await send_desktop_command(session, session_id, action)
            results.append(result)
        total_elapsed = time.time() - start_total
        
        latencies = [r["elapsed"] for r in results]
        print(f"  总耗时: {total_elapsed:.2f}s")
        print(f"  平均延迟: {statistics.mean(latencies):.2f}s")
        print(f"  吞吐量: {len(results)/total_elapsed:.1f} req/s")

async def main():
    print("=" * 60)
    print("DesktopController 并发性能测试")
    print("=" * 60)
    
    # 等待服务启动
    async with aiohttp.ClientSession() as session:
        for i in range(10):
            try:
                async with session.get(f"{BASE_URL}/system/health", timeout=5) as resp:
                    if resp.status == 200:
                        print("✅ 服务已就绪")
                        break
            except:
                pass
            await asyncio.sleep(1)
            print(f"  等待服务启动... {i+1}/10")
    
    # 测试1: 5并发 x 20请求
    await test_concurrent_requests(num_concurrent=5, num_requests=20)
    
    # 测试2: 10并发 x 30请求
    await test_concurrent_requests(num_concurrent=10, num_requests=30)
    
    # 测试3: 顺序请求对比
    await test_sequential_requests(num_requests=10)
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
