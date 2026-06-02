import asyncio
import json
import uuid

import httpx

# Configuration
BASE_URL = "http://127.0.0.1:8000"
TOKEN = "MDAwMDAwMDAwMJmvg62RumKdio-wnJO4tM6DoKfUf9OvrL2KfpO-jpthlY1qpYDNoKx-sb9qf6XG3YF6r9iCqaufyHt608eluJeYfaWtkbZ6an2LyWiBpayVgbDJ24OukXA"
PROJECT_ID = 30
THREAD_ID = str(uuid.uuid4())

print(f"Starting Test Thread: {THREAD_ID}")

async def listen_sse(client, thread_id):
    """
    Connects to SSE stream and listens for 'activity' events.
    Returns when 'human_request' is found.
    """
    url = f"{BASE_URL}/api/v1/stream/chat/{thread_id}"
    print(f"Connecting to SSE: {url}")

    async with client.stream("GET", url, headers={"Authorization": f"Bearer {TOKEN}"}) as response:
        async for line in response.aiter_lines():
            if line.startswith("event: activity"):
                # Next line should be data
                continue
            if line.startswith("data: "):
                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                    # Check for Human Request
                    if data.get("human_request"):
                        print("\n[SSE] Human Request Detected!")
                        print(json.dumps(data["human_request"], indent=2))
                        return data["human_request"]

                    # Log tasks progress
                    if data.get("tasks"):
                         tasks = data["tasks"]
                         # simple log of last task status
                         if tasks:
                             last = tasks[-1]
                             print(f"\r[SSE] Task: {last.get('title')} ({last.get('status')})", end="", flush=True)

                except Exception:
                    pass

async def wait_for_server(client):
    """Polls server until it is ready."""
    print(f"[Client] Waiting for server at {BASE_URL}...")
    for i in range(30):
        try:
            resp = await client.get(f"{BASE_URL}/docs")
            if resp.status_code == 200:
                print("[Client] Server is Ready!")
                return True
        except Exception:
            pass
        await asyncio.sleep(2)
        print(".", end="", flush=True)
    print("\n[Client] Server failed to start in 60s.")
    return False

async def main():
    async with httpx.AsyncClient(timeout=120.0) as client:
        if not await wait_for_server(client):
            return

        # 1. Start Chat
        chat_payload = {
            "thread_id": THREAD_ID,
            "message": "Generate a complete wiki for this project.",
            "project_id": PROJECT_ID
        }

        print("\n[Client] Sending 'Generate Wiki' request...")
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "X-Guest-Id": "test-guest"
        }
        resp = await client.post(f"{BASE_URL}/api/v1/chat", json=chat_payload, headers=headers)
        if resp.status_code != 200:
            print(f"Error starting chat: {resp.status_code} {resp.text}")
            return

        print(f"[Client] Chat started. Listening for approval... (Thread: {THREAD_ID})")

        # 2. Listen for Approval
        # We need to run listen_sse in a way that we can continue
        # But listen_sse returns only when approval is found.
        # So we await it.
        human_req = await listen_sse(client, THREAD_ID)

        if not human_req:
            print("[Client] No approval request received (Stream ended?). Test Failed.")
            return

        print("\n[Client] Approval Request Received. Sending 'Approve' (after 2s delay)...")
        await asyncio.sleep(2) # Simulate human delay

        # 3. Resume (Approve)
        resume_payload = {
            "thread_id": THREAD_ID,
            "user_input": "yes"
        }
        resp = await client.post(f"{BASE_URL}/api/v1/chat/resume", json=resume_payload, headers=headers)
        if resp.status_code != 200:
            print(f"Error resuming chat: {resp.status_code} {resp.text}")
            return

        print("[Client] 'Approve' sent. Listening for completion...")

        # 4. Listen for Completion (optional, or just wait a bit)
        # Re-connect to SSE to see progress
        # For this test, valid success is getting the approval first.
        print("[Client] Test Passed: Approval Flow Triggered & Resume Sent.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
