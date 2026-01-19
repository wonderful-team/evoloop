import argparse
import sys
import time

import requests

BASE_URL = "http://localhost:8000/api/v1"

def chat(message, thread_id, project_id, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1. Send Chat Request
    payload = {
        "thread_id": thread_id,
        "message": message,
        "project_id": project_id
    }

    print(f"Sending User Message: {message}")
    resp = requests.post(f"{BASE_URL}/chat", json=payload, headers=headers)

    if resp.status_code != 200:
        print(f"Error sending chat: {resp.status_code} {resp.text}")
        sys.exit(1)

    print("Request Queued. Polling for response...")

    # 2. Poll for AI Response
    last_msg_count = 0

    # Get initial count
    resp = requests.get(f"{BASE_URL}/conversations/{thread_id}/messages", headers=headers)
    if resp.status_code == 200:
        msgs = resp.json()
        last_msg_count = len(msgs)

    # Wait for new message
    retries = 30 # 30 * 2s = 60s timeout
    while retries > 0:
        time.sleep(2)
        resp = requests.get(f"{BASE_URL}/conversations/{thread_id}/messages", headers=headers)
        if resp.status_code == 200:
            msgs = resp.json()
            if len(msgs) > last_msg_count:
                # Found new messages
                new_msgs = msgs[last_msg_count:]

                # Filter for AI messages
                ai_reply = None
                for m in new_msgs:
                    if m["type"] == "ai":
                        ai_reply = m
                        print(f"\n[AI]: {m['content']}")
                        if m.get('steps_snapshot'):
                            print(f"[Steps Snapshot]: {len(m['steps_snapshot'])} items")

                if ai_reply:
                    return # Done
        retries -= 1
        print(".", end="", flush=True)

    print("\nTimeout waiting for response.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--msg", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--project", type=int, default=7)
    parser.add_argument("--thread", default="dynamic-test-v1")

    args = parser.parse_args()

    chat(args.msg, args.thread, args.project, args.token)
