#!/usr/bin/env python3
"""
Test raw SSE through Gateway to see how many chunks are received.
Run this BEFORE and AFTER adding User-Agent header to the provider config.
"""
import json
import httpx

# Config
GATEWAY_URL = "https://evoloop.develop-assistant.cn/gateway/v1/chat/completions"
TOKEN = "MDAwMDAwMDAwMJmvg62RumKdio-wnJO4tM6DoKfUf9OvrL2KfpO-jpthlY1qpYDNoKx-sclpf9u4lYJ6r5aCqaufyHt608eluJeYfaWtkbZ6an2LyWmA27jegrCr24W-kXA"  # or your actual Bearer token

# Request body (forces tool call)
body = {
    "model": "kimi-k2-thinking-turbo",
    "messages": [
        {"role": "system", "content": "You MUST use the route_to tool in EVERY response. Never reply with plain text."},
        {"role": "user", "content": "你是谁？"}
    ],
    "stream": True,
    "tools": [{
        "type": "function",
        "function": {
            "name": "route_to",
            "description": "Route to a specific node",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target node"},
                    "reason": {"type": "string", "description": "Reason"}
                },
                "required": ["target", "reason"]
            }
        }
    }],
    "tool_choice": "required",
    "temperature": 0.3,
}


async def test():
    print("=" * 60)
    print("TEST: Raw SSE through Gateway")
    print(f"URL: {GATEWAY_URL}")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            GATEWAY_URL,
            json=body,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            }
        )

        print(f"HTTP Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print()

        chunks = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    chunks.append(obj)
                except:
                    pass

        print(f"Total SSE events received: {len(chunks)}")
        print()

        # Detailed analysis
        tool_call_chunks = 0
        content_chunks = 0
        for i, c in enumerate(chunks):
            choices = c.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                tc = delta.get("tool_calls")
                content = delta.get("content")
                fr = choices[0].get("finish_reason")

                if tc:
                    tool_call_chunks += 1
                    print(f"  chunk[{i}] tool_calls={json.dumps(tc, ensure_ascii=False)[:120]}")
                if content:
                    content_chunks += 1
                if fr:
                    print(f"  chunk[{i}] finish_reason={fr}")

        print()
        print(f"Summary: content_events={content_chunks}, tool_call_events={tool_call_chunks}")

        if chunks:
            last = chunks[-1]
            choices = last.get("choices", [])
            if choices:
                fr = choices[0].get("finish_reason")
                if fr == "tool_calls" and tool_call_chunks == 0:
                    print("\n  🐛 BUG CONFIRMED: finish_reason=tool_calls but NO tool_call chunks!")
                elif fr == "tool_calls" and tool_call_chunks > 0:
                    print(f"\n  ✅ WORKING: {tool_call_chunks} tool_call chunks received")
                else:
                    print(f"\n  ℹ️  finish_reason={fr}, tool_call_chunks={tool_call_chunks}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test())
