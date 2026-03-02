import requests
import json
import time
import uuid

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
GUEST_ID = f"test-guest-{uuid.uuid4().hex[:8]}"
THREAD_ID = f"xianyu-task-trigger-{int(time.time())}"
INSTRUCTION = "每天中午12点爬取闲鱼最新上架商品数据"


def trigger_agent_mission():
    headers = {
        "X-Guest-Id": GUEST_ID,
        "Content-Type": "application/json"
    }

    # 1. Send Chat Request to trigger the Agent
    payload = {
        "thread_id": THREAD_ID,
        "message": INSTRUCTION,
        "project_id": 1
    }

    print(f"🚀 发送指令到 EvoLoop Agent: '{INSTRUCTION}'")
    print(f"🧵 Thread ID: {THREAD_ID}")
    
    try:
        resp = requests.post(f"{BASE_URL}/chat", json=payload, headers=headers)
        if resp.status_code != 200:
            print(f"❌ 发送失败: {resp.status_code} - {resp.text}")
            return
        print("✅ 指令已送达，Agent 正在后台处理...")
    except Exception as e:
        print(f"❌ 无法连接到 EvoLoop 后端: {e}")
        return

    # 2. Polling for progress (Simulating user watching the chat)
    print("\n🧐 正在监控 Agent 执行过程 (轮询消息列表)...")
    
    last_count = 0
    start_time = time.time()
    timeout = 3600  # 60 minutes for complex reasoning and tool execution
    
    while time.time() - start_time < timeout:
        try:
            # Poll conversation messages
            msg_resp = requests.get(f"{BASE_URL}/conversations/{THREAD_ID}/messages", headers=headers)
            if msg_resp.status_code == 200:
                messages = msg_resp.json()
                if len(messages) > last_count:
                    # Print new messages
                    for m in messages[last_count:]:
                        role = m.get("role", "unknown").upper()
                        content = m.get("content", "")
                        print(f"\n[{role}]: {content[:500]}..." if len(content) > 500 else f"\n[{role}]: {content}")
                        
                        # Check for success/finish signals
                        if role == "AI" and ("任务已创建" in content or "建立" in content or "完成" in content):
                            print("\n✨ Agent 报告任务处理完成！")
                            return
                    last_count = len(messages)
            
            # Print a dot to show activity
            print(".", end="", flush=True)
            time.sleep(5)
            
        except Exception as e:
            print(f"\n⚠️ 轮询出错: {e}")
            time.sleep(5)

    print(f"\n⌛ 监控超时 ({timeout}s)。Agent 可能仍在后台执行，请检查 Crawler 数据库。")


if __name__ == "__main__":
    trigger_agent_mission()
