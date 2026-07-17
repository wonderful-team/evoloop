"""并发真实全链路 E2E：暴露 SQLite/执行引擎的竞态与锁问题。

3 个线程同时发同一句 web 读宏，看是否出现 database locked、执行串扰、
结果丢失或超时。

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=admin888 \\
        .venv/bin/python tests/manual/voice_chain_concurrent_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

WS_PORT = 18315
BASE = "http://127.0.0.1:9002"
WS_URL = f"ws://127.0.0.1:{WS_PORT}/api/v1/voice/ws"
TEXT = "查一下夜光亚克力钥匙扣的价格"
CONCURRENCY = 3


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


async def _one_client(idx: int, results: list):
    import websockets

    thread = f"concurrent-{idx}"
    async with websockets.connect(WS_URL) as ws:
        await ws.recv()
        t0 = time.monotonic()
        await ws.send(json.dumps(_body("voice.route", {"thread_id": thread, "text": TEXT})))
        body = await _recv(ws, lambda b, t=thread: b.get("thread_id") == t and "status" in b, 120)
        if body.get("status") == "routed" and body.get("target", {}).get("type") in ("macro", "skill", "agent"):
            body = await _recv(ws, lambda b, t=thread: b.get("thread_id") == t and b.get("status") in ("done", "failed"), 180)
        total = (time.monotonic() - t0) * 1000
        results.append((idx, body.get("status"), total, body.get("summary", "")[:60]))


async def main():
    import uvicorn
    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=WS_PORT, log_level="error"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.2)

    try:
        await _login()
        print(f"[concurrent-e2e] {CONCURRENCY} 线程同时发送: {TEXT!r}\n")
        results: list = []
        t0 = time.monotonic()
        await asyncio.gather(*[_one_client(i, results) for i in range(CONCURRENCY)])
        elapsed = (time.monotonic() - t0) * 1000
        print(f"── 并发完成，总耗时 {elapsed:.0f}ms ──")
        for idx, status, ms, summary in sorted(results):
            ok = status == "done"
            print(f"{'PASS' if ok else 'FAIL'} thread-{idx}: {status} ({ms:.0f}ms) {summary}")
        print(f"\n汇总: {sum(1 for _, s, _, _ in results if s == 'done')}/{CONCURRENCY}")
    finally:
        server.should_exit = True
        await task


if __name__ == "__main__":
    asyncio.run(main())
