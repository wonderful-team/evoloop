import requests
import json

thread_id = "095e347f-5385-455b-b143-3093ff31b020"
url = "http://127.0.0.1:8001/api/v1/chat/resume"

payload = {
    "thread_id": thread_id,
    "user_input": "APPROVED"
}

headers = {
    "Content-Type": "application/json"
}

print(f"Resuming thread {thread_id} with approval...")
try:
    response = requests.post(url, json=payload, headers=headers)
    print("Status:", response.status_code)
    print("Body:", response.text)
except Exception as e:
    print("Exception:", e)
