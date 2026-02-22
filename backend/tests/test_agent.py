import requests
import uuid

thread_id = str(uuid.uuid4())
url = "http://127.0.0.1:8000/api/v1/chat"
headers = {
    "Content-Type": "application/json",
    "x-guest-id": f"guest-test-{uuid.uuid4().hex[:8]}"
}

payload = {
    "thread_id": thread_id,
    "message": "打开 Chrome 查一下最新的 AI 新闻，把摘要存到剪贴板，然后打开微信发给其中的“文件传输助手”",
    "project_id": 1
}

print(f"Sending request to {url}\nThread ID: {thread_id}\nPayload: {payload}")
try:
    response = requests.post(url, json=payload, headers=headers)
    print("Status:", response.status_code)
    print("Body:", response.text)
except Exception as e:
    print("Exception:", e)
