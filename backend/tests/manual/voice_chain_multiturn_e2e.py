"""真实多轮对话 E2E：同一线程内上下文连续传递。

场景：
  T1: 查一下它的价格        -> clarify（缺少实体）
  T2: 夜光亚克力钥匙扣      -> done，建立 current_entity
  T3: 那库存呢              -> anaphora 续接，done
  T4: 这个售价是多少        -> anaphora 续接，done

验证 session_frame 在多轮 voice.route 中持续生效。

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=admin888 \\
        .venv/bin/python tests/manual/voice_chain_multiturn_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

WS_PORT = 18316
BASE = "http://127.0.0.1:9002"
WS_URL = f"ws://127.0.0.1:{WS_PORT}/api/v1/voice/ws"


def _env(k, d=""):
    return os.environ.get(k, d)


def _body(type_, body):
    return {
        "version": "2.0",
        "type": type_,
        "message_id": uuid.uuid4().hex,
        "timestamp": int(time.time()),
        "body": body,
    }


async def _recv(ws, pred, timeout=120):
    dl = time.monotonic() + timeout
    while True:
        left = dl - time.monotonic()
        if left <= 0:
            raise TimeoutError("ws")
        data = await asyncio.wait_for(ws.recv(), timeout=left)
        env = json.loads(data)
        b = env.get("body") or env
        if env.get("type") == "voice.route_result" and pred(b):
            return b


async def _login():
    from app.infrastructure.drivers.browser import browser_manager

    page = await browser_manager.get_page()
    await page.goto(f"{BASE}/shop.html", wait_until="load", timeout=30000)
    await page.wait_for_timeout(1000)
    if "login" in page.url:
        await page.fill("[name='username']", _env("MALL_ADMIN_USER", "admin"))
        await page.fill("[name='password']", _env("MALL_ADMIN_PASS", "admin888"))
        await page.click("[lay-filter='login']")
        await page.wait_for_timeout(3000)
    assert "login" not in page.url


TURNS = [
    {"label": "T1", "text": "查一下它的价格", "expect": "clarify"},
    {"label": "T2", "text": "夜光亚克力钥匙扣", "expect": "done"},
    {"label": "T3", "text": "那库存呢", "expect": "done"},
    {"label": "T4", "text": "这个售价是多少", "expect": "done"},
]


async def main():
    import uvicorn
    import websockets
    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=WS_PORT, log_level="error"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.2)

    try:
        await _login()
        print("[multiturn-e2e] 商城登录态 OK\\n")

        async with websockets.connect(WS_URL) as ws:
            await ws.recv()  # system.init
            thread = "multiturn-thread"
            results = []
            for turn in TURNS:
                try:
                    t0 = time.monotonic()
                    await ws.send(json.dumps(_body("voice.route", {"thread_id": thread, "text": turn["text"]})))
                    body = await _recv(ws, lambda b, t=thread: b.get("thread_id") == t and "status" in b, 120)
                    if body.get("status") == "routed" and body.get("target", {}).get("type") in ("macro", "skill", "agent"):
                        body = await _recv(ws, lambda b, t=thread: b.get("thread_id") == t and b.get("status") in ("done", "failed", "clarify"), 120)
                    status = body.get("status")
                    ok = status == turn["expect"]
                    ms = (time.monotonic() - t0) * 1000
                except Exception as e:
                    ok = False
                    status = f"exception:{type(e).__name__}"
                    ms = 0
                results.append((turn["label"], turn["text"], ok, status, ms))
                print(f"{'PASS' if ok else 'FAIL'} [{turn['label']}] {turn['text']!r} -> {status} ({ms:.0f}ms)")
                await asyncio.sleep(1.0)

            passed = sum(1 for _, _, ok, _, _ in results if ok)
            print(f"\\n── 多轮汇总 {passed}/{len(results)} ──")
            for label, text, ok, status, ms in results:
                print(f"  {'✓' if ok else '✗'} {label}: {text!r} -> {status} ({ms:.0f}ms)")
    finally:
        server.should_exit = True
        await task


if __name__ == "__main__":
    asyncio.run(main())
