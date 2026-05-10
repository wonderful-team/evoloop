import asyncio
import json
import os
import sys
from datetime import datetime

# 强制设置环境为非嵌入模式，以启用 Redis
os.environ["EMBEDDED_MODE"] = "false"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

sys.path.append(os.path.join(os.getcwd(), "evoloop/backend"))

from app.infrastructure.cache import RedisCache
from app.infrastructure.queue.event_bus import RedisEventBus

async def observe_real_stream():
    # 直接构造 RedisEventBus 以确保监听物理 Redis
    cache = RedisCache(url=os.environ["REDIS_URL"])
    bus = RedisEventBus(cache)
    
    print(f"[{datetime.now()}] REAL-TIME OBSERVER ACTIVE (Redis: {os.environ['REDIS_URL']})")
    print("Watching for tool execution streams...\n")
    
    pubsub = bus.client.pubsub()
    # 监听所有消息频道
    await pubsub.psubscribe("chat:*:events")
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                try:
                    data = json.loads(message["data"])
                    # SSE 协议中，消息在 data 字段下
                    event_data = data.get("data", {})
                    role = event_data.get("role")
                    
                    if role == "tool":
                        status = event_data.get("status")
                        tool_name = event_data.get("metadata", {}).get("tool_name")
                        seq = event_data.get("sequence_number")
                        
                        print(f"DEBUG: Received tool event: {tool_name}, status: {status}, seq: {seq}")
                        
                        if status == "running":
                            print(f"🟢 [TOOL_START] {datetime.now().strftime('%H:%M:%S.%f')}")
                            print(f"   Tool: {tool_name}")
                            print(f"   Seq:  {seq}")
                        elif status == "completed":
                            print(f"✅ [TOOL_END]   {datetime.now().strftime('%H:%M:%S.%f')}")
                            print(f"   Tool: {tool_name}")
                            print(f"   Seq:  {seq}")
                            print(f"   Output: {str(event_data.get('content'))[:100]}...")
                        print("-" * 50)
                except Exception as e:
                    continue
    except Exception as e:
        print(f"Observer error: {e}")

if __name__ == "__main__":
    asyncio.run(observe_real_stream())
