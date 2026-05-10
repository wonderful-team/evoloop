import asyncio
import json
import os
import sys
from datetime import datetime

# 确保能找到 app 模块
sys.path.append(os.path.join(os.getcwd(), "evoloop/backend"))

from app.core.engine.message.event_bus import get_event_bus

async def observe_real_stream(thread_id_prefix="stress-test"):
    bus = get_event_bus()
    # 订阅所有压力测试线程的消息（通过通配符或动态获取）
    # 注意：Redis 订阅需要具体频道名，我们会通过监听所有事件频道来获取
    print(f"[{datetime.now()}] Observer started. Waiting for tool events...")
    
    pubsub = bus.client.pubsub()
    await pubsub.psubscribe("chat:stress-test-*:events")
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                data = json.loads(message["data"])
                msg_data = data.get("data", {})
                role = msg_data.get("role")
                status = msg_data.get("status")
                
                if role == "tool":
                    print(f"\n[STREAM EVIDENCE] {datetime.now().strftime('%H:%M:%S.%f')}")
                    print(f"Thread: {message['channel'].decode()}")
                    print(f"Action: {data.get('action')}")
                    print(f"Tool: {msg_data.get('metadata', {}).get('tool_name')}")
                    print(f"Status: {status}")
                    print(f"Content Preview: {str(msg_data.get('content'))[:50]}...")
                    print("-" * 30)
    except Exception as e:
        print(f"Observer error: {e}")

if __name__ == "__main__":
    import sys
    # 获取第一个参数作为前缀
    prefix = sys.argv[1] if len(sys.argv) > 1 else "stress-test"
    asyncio.run(observe_real_stream(prefix))
