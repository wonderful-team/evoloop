import requests
import uuid
import sys

# Default configuration
SERVER_URL = "http://127.0.0.1:8000/api/v1/chat"
THREAD_ID = str(uuid.uuid4())
GUEST_ID = f"guest-mobile-{uuid.uuid4().hex[:8]}"

# Mobile Scenarios
SCENARIOS = {
    "1": "打开手机设置，进入 WLAN 界面，帮我确认一下 Wi-Fi 是否已经连接。",
    "2": "帮我看看手机系统设置里‘关于手机’的部分，告诉我当前的安卓版本号是多少？",
    "3": "进入手机设置，找到‘显示’选项，并尝试调整一下刷新率或亮度（仅作为导航测试）。",
    "4": "打开微信，帮我给‘文件传输助手’发一条消息，内容是：‘这是一条来自 EvoLoop 移动端 Reactor 的自动化测试消息’。"
}

def run_scenario(scenario_id="1"):
    message = SCENARIOS.get(scenario_id, SCENARIOS["1"])
    
    headers = {
        "Content-Type": "application/json",
        "x-guest-id": GUEST_ID
    }

    payload = {
        "thread_id": THREAD_ID,
        "message": message,
        "project_id": 1
    }

    print("="*60)
    print(f"🚀 STARTING MOBILE SCENARIO {scenario_id}")
    print(f"Message: {message}")
    print(f"Thread ID: {THREAD_ID}")
    print("="*60)

    try:
        # Note: This assumes the backend server is running
        response = requests.post(SERVER_URL, json=payload, headers=headers, timeout=120)
        print(f"STATUS: {response.status_code}")
        print("-" * 30)
        print("AGENT RESPONSE:")
        print(response.json().get("reply", response.text))
        print("-" * 30)
    except Exception as e:
        print(f"❌ ERROR: Failed to connect to backend at {SERVER_URL}")
        print(f"Details: {e}")
        print("\n💡 Tip: Make sure to start the backend server with `npm run dev` or equivalent first.")

if __name__ == "__main__":
    sid = "1"
    if len(sys.argv) > 1:
        sid = sys.argv[1]
    run_scenario(sid)
