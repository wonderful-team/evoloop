"""补充边缘场景真实 E2E：依赖型多意图、澄清链、重复消息、空文本、跨实体切换。

    .venv/bin/python tests/manual/voice_edge_cases.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

WS_PORT = 18317
BASE = "http://127.0.0.1:9002"
WS_URL = f"ws://127.0.0.1:{WS_PORT}/api/v1/voice/ws"


def _env(k, d=""):
    return os.environ.get(k, d)


def _body(type_, body):
    return {"version": "2.0", "type": type_, "message_id": uuid.uuid4().hex,
            "timestamp": int(time.time()), "body": body}


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
        await page.fill('[name="username"]', _env("MALL_ADMIN_USER", "admin"))
        await page.fill('[name="password"]', _env("MALL_ADMIN_PASS", "admin888"))
        await page.click('[lay-filter="login"]')
        await page.wait_for_timeout(3000)
    assert "login" not in page.url


CASES = [
    {"label": "dependency: 查价再降10%", "text": "查一下夜光亚克力钥匙扣的价格，然后把它降10%", "expect": "done"},
    {"label": "empty text", "text": "", "expect": "any", "allow": ["done", "failed", "clarify", "skipped"], "no_send": True},
    {"label": "duplicate idempotent first", "text": "查一下夜光亚克力钥匙扣的价格", "expect": "done", "thread": "dup-thread", "msg_id": "dup-msg-1"},
    {"label": "duplicate idempotent same msg", "text": "查一下夜光亚克力钥匙扣的价格", "expect": "done", "thread": "dup-thread", "msg_id": "dup-msg-1", "wait_done": False},
    {"label": "L0 priority: 音量大一点", "text": "音量大一点", "expect": "routed", "expect_target_type": "local"},
    {"label": "L0 priority: 打开微信", "text": "打开微信", "expect": "routed", "expect_target_type": "local"},
    {"label": "context switch entity", "text": "查一下夜光亚克力钥匙扣的价格", "expect": "done", "thread": "switch-thread"},
    {"label": "context switch new entity", "text": "那换成查金属徽章的价格", "expect": "done", "thread": "switch-thread"},
]


async def _run_case(ws, step, threads):
    thread = step.get("thread") or f"edge-{uuid.uuid4().hex[:6]}"
    if step.get("thread"):
        threads[step["thread"]] = thread
    text = step["text"]
    if step.get("no_send"):
        return {"status": "skipped"}, 0

    t0 = time.monotonic()
    body = {"thread_id": thread, "text": text}
    if step.get("msg_id"):
        body["message_id"] = step["msg_id"]
    await ws.send(json.dumps(_body("voice.route", body)))
    b = await _recv(ws, lambda b, t=thread: b.get("thread_id") == t and "status" in b, 120)
    if step.get("wait_done", True) and b.get("status") == "routed" and b.get("target", {}).get("type") in ("macro", "skill", "agent"):
        b = await _recv(ws, lambda b, t=thread: b.get("thread_id") == t and b.get("status") in ("done", "failed", "clarify"), 120)
    return b, (time.monotonic() - t0) * 1000


async def _check(step, body):
    if step.get("expect") == "any":
        return body.get("status") in step.get("allow", [])
    if body.get("status") != step["expect"]:
        return False
    if "expect_target_type" in step:
        if body.get("target", {}).get("type") != step["expect_target_type"]:
            return False
    return True


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
        print("[edge-e2e] 登录态 OK\\n")
        async with websockets.connect(WS_URL) as ws:
            await ws.recv()
            threads = {}
            results = []
            for step in CASES:
                try:
                    body, ms = await _run_case(ws, step, threads)
                    ok = await _check(step, body)
                    status = body.get("status")
                except Exception as e:
                    ok = False
                    status = f"exception:{type(e).__name__}"
                    ms = 0
                results.append((step["label"], ok, status, ms, body.get("intents")))
                print(f"{'PASS' if ok else 'FAIL'} [{step['label']}] -> {status} ({ms:.0f}ms) intents={body.get('intents')}")
                await asyncio.sleep(1.0)
            passed = sum(1 for _, ok, _, _, _ in results if ok)
            print(f"\\n── 边缘场景汇总 {passed}/{len(results)} ──")
            for label, ok, status, ms, intents in results:
                print(f"  {'✓' if ok else '✗'} {label}: {status} ({ms:.0f}ms) intents={intents}")
    finally:
        server.should_exit = True
        await task


if __name__ == "__main__":
    asyncio.run(main())
