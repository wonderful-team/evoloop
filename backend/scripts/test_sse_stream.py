import asyncio
import argparse
import httpx
import json
import uuid

async def listen_to_sse(base_url: str, thread_id: str):
    url = f"{base_url}/stream/chat/{thread_id}"
    print(f"Connecting to SSE stream: {url}")
    
    timeout = httpx.Timeout(10.0, read=None)
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream('GET', url) as response:
                if response.status_code != 200:
                    print(f"Failed to connect. Status code: {response.status_code}")
                    content = await response.aread()
                    print(f"Response: {content.decode('utf-8')}")
                    return

                print("Connected! Listening for events...\n")
                
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    
                    if line.startswith("event: "):
                        event_type = line[7:]
                        print(f"[{event_type}]", end=" ")
                    elif line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            # Try to parse JSON for pretty printing
                            data = json.loads(data_str)
                            print(json.dumps(data, indent=2, ensure_ascii=False))
                        except json.JSONDecodeError:
                            # Print raw if not JSON
                            print(data_str)
                    else:
                        print(f"RAW: {line}")
                        
    except httpx.ReadTimeout:
        print("\nConnection timed out (no data received).")
    except asyncio.CancelledError:
        print("\nStream listening cancelled.")
    except Exception as e:
        print(f"\nError: {e}")

async def main():
    parser = argparse.ArgumentParser(description="Listen to Evoloop SSE chat stream.")
    parser.add_argument("--url", type=str, default="http://localhost:20160/api/v1", help="Base API URL")
    parser.add_argument("--thread-id", type=str, help="Specific thread ID to listen to. If not provided, generates a new one.")
    
    args = parser.parse_args()
    
    thread_id = args.thread_id or str(uuid.uuid4())
    print(f"Using Thread ID: {thread_id}")
    
    # You could optionally trigger a mock request here before listening, 
    # but normally you'd run this script in one terminal, and trigger the mock in another or via frontend.
    print(f"Hint: In another terminal, you can trigger a mock request to this thread:")
    print(f"curl -X POST {args.url}/chat/mock -H 'Content-Type: application/json' -d '{{\"thread_id\": \"{thread_id}\", \"scenario\": \"A\"}}'")
    print("-" * 50)
    
    await listen_to_sse(args.url, thread_id)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
