import requests
import json

base_url = "https://evoloop.develop-assistant.cn/member"
api_key = "1a42a0623e0ad1287c8c784f0124ec8e"

headers = {
    "X-Gateway-Key": api_key
}

try:
    resp = requests.get(f"{base_url}/api/gateway/llmConfig", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Error: {resp.status_code}, {resp.text}")
except Exception as e:
    print(f"Exception: {e}")
