"""E2E test: Python WS → voice.tts_boundary → Rust TTS → speaker.

Requires: Python backend running on :20160, Tauri/Rust frontend with WS connected.
"""

import asyncio
import json
import websockets

WS_URL = "ws://127.0.0.1:20160/api/v1/voice/ws"


async def test():
    async with websockets.connect(WS_URL) as ws:
        # 1. Receive handshake
        init = json.loads(await ws.recv())
        print(f"Handshake: {init['type']}")
        assert init["type"] == "system.init"

        # 2. Say hello
        await ws.send(json.dumps({
            "type": "connect",
            "body": {},
        }))

        # 3. Send a voice route to trigger full LLM → TTS path
        print("\n发送: voice.route → 触发 LLM 生成")
        await ws.send(json.dumps({
            "type": "voice.route",
            "body": {
                "thread_id": "e2e-test",
                "text": "你是谁",
                "message_id": "e2e-001",
            },
        }))

        # 4. Listen for all responses (timeout 15s)
        tts_sentences = []
        while True:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                mtype = msg.get("type", "")
                body = msg.get("body", {})

                if mtype == "voice.tts_boundary":
                    sentence = body.get("sentence", body.get("text", ""))
                    if sentence:
                        tts_sentences.append(sentence)
                        print(f"  tts_boundary: {sentence}")

                elif mtype == "voice.route_result":
                    status = body.get("status", "")
                    summary = body.get("summary", "")
                    print(f"  route_result: {status} → {summary[:50]}")
                    if status in ("done", "failed", "cancelled"):
                        break

            except asyncio.TimeoutError:
                print("\n⏱ Timeout - no more messages")
                break

        print(f"\n共 {len(tts_sentences)} 句 TTS 播报:")
        for s in tts_sentences:
            print(f"  🗣 {s}")

        if tts_sentences:
            print("\n✅ 全链路测试通过！")
        else:
            print("\n❌ 未收到 TTS 播报")


if __name__ == "__main__":
    asyncio.run(test())
