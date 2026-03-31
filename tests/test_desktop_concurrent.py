#!/usr/bin/env python3
"""
DesktopController 并发测试 - 测试异步性能
"""

import asyncio
import aiohttp
import time
import statistics
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"

# 使用现有会话
SESSION_ID = "e99fded6-2a5a-4c46-8b54-215aefc7cccf"

async def send_desktop_command(session, action, params=None):
    """发送桌面控制命令"""
    payload = {
        "input": f"测试命令: {action}",
        "context": {
            "session_id": SESSION_ID,
            "conversation_id": SESSION_ID,
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
            f"{BASE_URL}/chat", 
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            elapsed = time.time() - start
            status = resp.status
            try:
                data = await resp.json()
            except:
                data = {"text": await resp.text()[:200]}
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
            "error": str(e)[:100]
        }

async def test_concurrent_desktop(num_concurrent=5, num_requests=10):
    """测试桌面控制并发请求"""
    print(f"\n🚀 DesktopController 并发测试: {num_concurrent}并发 x {num_requests}请求")
    print(f"时间: {datetime.now().isoformat()}")
    print("-" * 60)
    
    async with aiohttp.ClientSession() as session:
        # 准备测试命令
        actions = ["get_info", "screenshot", "list_apps"] * (num_requests // 3 + 1)
        actions = actions[:num_requests]
        
        # 并发发送请求
        semaphore = asyncio.Semaphore(num_concurrent)
        
        async def bounded_request(action):
            async with semaphore:
                return await send_desktop_command(session, action)
        
        start_total = time.time()
        tasks = [bounded_request(action) for action in actions]
        results = await asyncio.gather(*tasks)
        total_elapsed = time.time() - start_total
        
        # 统计结果
        success_count = sum(1 for r in results if r["success"])
        fail_count = len(results) - success_count
        latencies = [r["elapsed"] for r in results]
        
        print(f"\n📊 测试结果:")
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
        
        return {
            "concurrent": num_concurrent,
            "requests": num_requests,
            "success_rate": success_count / len(results),
            "throughput": len(results) / total_elapsed,
            "avg_latency": statistics.mean(latencies),
            "max_latency": max(latencies)
        }

async def main():
    print("=" * 60)
    print("DesktopController 异步性能测试")
    print("=" * 60)
    
    # 检查服务状态
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{BASE_URL}/system/health", timeout=5) as resp:
                if resp.status == 200:
                    print("✅ 服务已就绪\n")
                else:
                    print(f"⚠️ 服务状态异常: {resp.status}")
                    return
        except Exception as e:
            print(f"❌ 无法连接到服务: {e}")
            return
    
    # 运行多轮测试
    all_results = []
    
    # 测试1: 低并发
    result = await test_concurrent_desktop(num_concurrent=3, num_requests=9)
    all_results.append(result)
    
    await asyncio.sleep(2)
    
    # 测试2: 中等并发
    result = await test_concurrent_desktop(num_concurrent=5, num_requests=15)
    all_results.append(result)
    
    await asyncio.sleep(2)
    
    # 测试3: 高并发
    result = await test_concurrent_desktop(num_concurrent=8, num_requests=24)
    all_results.append(result)
    
    # 总结
    print("\n" + "=" * 60)
    print("📈 性能测试总结")
    print("=" * 60)
    print(f"{'并发数':>8} | {'请求数':>8} | {'成功率':>8} | {'吞吐(req/s)':>12} | {'平均延迟(s)':>12}")
    print("-" * 60)
    for r in all_results:
        print(f"{r['concurrent']:>8} | {r['requests']:>8} | {r['success_rate']*100:>7.1f}% | {r['throughput']:>12.1f} | {r['avg_latency']:>12.2f}")
    
    print("\n✅ 测试完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
