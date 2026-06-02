import asyncio
import argparse
import httpx
import json
import uuid
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("verify_e2e")

async def listen_to_sse(base_url: str, thread_id: str, events_record: list):
    url = f"{base_url}/stream/chat/{thread_id}"
    logger.info(f"Connecting to SSE stream: {url}")
    
    timeout = httpx.Timeout(300.0, read=None) # 5 minutes timeout for analytics task
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream('GET', url) as response:
                if response.status_code != 200:
                    logger.error(f"Failed to connect to SSE. Status code: {response.status_code}")
                    content = await response.aread()
                    logger.error(f"Response: {content.decode('utf-8')}")
                    return

                logger.info("SSE Connected! Listening for events...\n")
                
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    
                    if line.startswith("event: "):
                        event_type = line[7:]
                        events_record.append({"type": event_type, "raw_data": None})
                    elif line.startswith("data: "):
                        data_str = line[6:]
                        if events_record:
                            events_record[-1]["raw_data"] = data_str
                        try:
                            data = json.loads(data_str)
                            if events_record:
                                events_record[-1]["data"] = data
                            
                            # Print concisely
                            msg_id = data.get("message_id", "N/A")
                            event_type = events_record[-1]["type"]
                            
                            if event_type in ["token", "thinking"]:
                                # don't print every token, just print dots or a summary
                                pass
                            else:
                                logger.info(f"[{event_type}] msg_id: {msg_id} - {data_str[:200]}...")
                                
                            if event_type == "session_completed":
                                logger.info("Session completed. Exiting SSE listener.")
                                break
                                
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse JSON data: {data_str}")
                        
    except Exception as e:
        logger.error(f"SSE Listener Error: {e}")

async def main():
    parser = argparse.ArgumentParser(description="End-to-End SSE Analytics Verification")
    parser.add_argument("--url", type=str, default="http://localhost:20160/api/v1", help="Base API URL")
    
    args = parser.parse_args()
    
    thread_id = f"analytics-e2e-{uuid.uuid4().hex[:6]}"
    logger.info(f"Using Thread ID: {thread_id}")
    
    events_record = []
    
    # 1. Start SSE listener in background
    sse_task = asyncio.create_task(listen_to_sse(args.url, thread_id, events_record))
    
    # Give the listener a moment to connect
    await asyncio.sleep(2)
    
    # 2. Trigger Chat POST request
    chat_url = f"{args.url}/chat"
    payload = {
        "thread_id": thread_id,
        "message": "随便写个 PHP 的脚本",
        "project_id": 99,
        "model": "kimi-k2-thinking-turbo"
    }
    
    logger.info(f"Triggering Chat request to {chat_url}...")
    async with httpx.AsyncClient() as client:
        # Note: We assume the backend allows guest access or we don't need auth for local test based on deps.py
        # You may need to add auth headers if verify_guest_access strictly requires it.
        try:
            response = await client.post(chat_url, json=payload, timeout=30.0)
            if response.status_code != 200:
                logger.error(f"Chat request failed: {response.status_code} - {response.text}")
                return
            logger.info(f"Chat request queued successfully. Response: {response.json()}")
        except Exception as e:
            logger.error(f"Chat request error: {e}")
            return
            
    # 3. Wait for the SSE stream to complete (or timeout)
    logger.info("Waiting for agent to process and stream results...")
    await asyncio.wait([sse_task], timeout=300)
    
    # 4. Verify message_id consistency
    logger.info("=" * 60)
    logger.info("📊 SSE EVENT ID VERIFICATION")
    logger.info("=" * 60)
    
    ai_message_id_map = {} # seq -> msg_id
    tool_message_id_map = {} # seq -> msg_id
    
    errors = 0
    
    for idx, ev in enumerate(events_record):
        data = ev.get("data", {})
        if not data:
            continue
            
        ev_type = ev["type"]
        msg_id = data.get("message_id")
        
        # We skip ping or general events that don't map to a specific message sequence
        if not msg_id:
            continue
            
        role = "unknown"
        # Attempt to infer role or sequence if available
        if ev_type in ["token", "thinking"]:
            role = "ai"
        elif ev_type in ["tool_output", "tool_error"]:
            role = "tool"
        elif ev_type == "status":
            role = data.get("role", "unknown")
            
        # Simplistic verification: 
        # Check if message_id changes unexpectedly during a sequence of AI events
        # We just log all unique message_ids seen.
        logger.debug(f"Event: {ev_type}, message_id: {msg_id}")
        
    unique_msg_ids = set()
    for ev in events_record:
        msg_id = ev.get("data", {}).get("message_id")
        if msg_id:
            unique_msg_ids.add(msg_id)
            
    logger.info(f"Total unique message_ids seen in SSE: {len(unique_msg_ids)}")
    for mid in unique_msg_ids:
        logger.info(f" - {mid}")
        
    logger.info("End of E2E verification.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nExiting...")
