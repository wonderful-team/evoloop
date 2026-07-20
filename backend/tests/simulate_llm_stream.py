import asyncio
import json
import websockets

# Constants from actual backend logic
SENTENCE_BOUNDARIES = "。！？.!?\n…"

async def simulate_llm_generation(websocket, thread_id: str):
    """
    Simulates the token-by-token generation of an LLM.
    We push `voice.token` character by character, and when we hit a boundary,
    we push `voice.tts_boundary`.
    """
    text = "你好，主人。我正在测试模拟真实的大模型推流。这个推流是逐字生成的，当遇到标点符号时，会作为一个完整的句子发送给 Rust 播放。你现在能听到我的声音了吗？"
    
    print(f"Starting simulation for thread: {thread_id}")
    buffer = ""
    for idx, char in enumerate(text):
        buffer += char
        # Simulate generation delay (~50ms per token, roughly 20 tokens/sec)
        await asyncio.sleep(0.05)
        
        # Send raw token event (just like VoiceChannel does)
        try:
            await websocket.send(json.dumps({
                "type": "voice.token",
                "body": {
                    "thread_id": thread_id,
                    "text": char,
                    "index": idx
                }
            }))
        except Exception as e:
            print(f"Failed to send token: {e}")
            return
            
        # Check boundary logic (same as VoiceChannel)
        if any(b in char for b in SENTENCE_BOUNDARIES):
            sentence = buffer.strip()
            if sentence:
                print(f"\n➡️ Boundary reached, pushing sentence to TTS: {sentence}")
                await websocket.send(json.dumps({
                    "type": "voice.tts_boundary",
                    "body": {
                        "thread_id": thread_id,
                        "sentence": sentence,
                        "text": sentence,
                        "index": idx
                    }
                }))
            buffer = ""
            
    # Flush remaining buffer if any
    if buffer.strip():
        sentence = buffer.strip()
        print(f"\n➡️ Flushing remaining sentence to TTS: {sentence}")
        await websocket.send(json.dumps({
            "type": "voice.tts_boundary",
            "body": {
                "thread_id": thread_id,
                "sentence": sentence,
                "text": sentence,
                "index": len(text)
            }
        }))
        
    print("Simulation complete. Sending done event.")
    await websocket.send(json.dumps({
        "type": "voice.route_result",
        "body": {
            "thread_id": thread_id,
            "status": "done",
            "summary": text
        }
    }))


async def handler(websocket):
    print("Rust client connected.")
    # Handshake
    conn_id = "test-sim-client"
    await websocket.send(json.dumps({
        "type": "system.init",
        "body": {"client_id": conn_id, "device_key": "simulated"}
    }))
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                mtype = data.get("type", "")
                print(f"Received from Rust: {mtype}")
                
                if mtype == "connect" or mtype == "system.init":
                    await websocket.send(json.dumps({
                        "type": "system.init",
                        "body": {"client_id": conn_id, "ack": True}
                    }))
                    
                elif mtype == "voice.route":
                    thread_id = data.get("body", {}).get("thread_id", "sim-thread")
                    print(f"Rust requested voice.route. Starting LLM simulation...")
                    # Run simulation in the background so we can still receive messages
                    asyncio.create_task(simulate_llm_generation(websocket, thread_id))
                    
            except json.JSONDecodeError:
                print(f"Invalid JSON received: {message}")
                
    except websockets.exceptions.ConnectionClosed:
        print("Rust client disconnected.")


async def main():
    port = 20160
    print(f"Starting mock backend WebSocket server on ws://127.0.0.1:{port}/api/v1/voice/ws")
    
    # Start the server on root (the rust client will connect to /api/v1/voice/ws but websockets module ignores path by default unless specified)
    async with websockets.serve(handler, "127.0.0.1", port):
        print("Server is listening. Please ensure the real backend is NOT running, then restart the Rust frontend.")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
