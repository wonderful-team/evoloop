"""全链路多样性 E2E（真实 uvicorn+websocket）。

覆盖：本地动作、原生宏、Web 读宏、指代续接、路由缓存命中、澄清复接、
原生应用偏置。每个用例独立失败不阻断后续；输出汇总表。

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=admin888 \
        .venv/bin/python tests/manual/voice_chain_exhaustive_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

WS_PORT = 18313
BASE = "http://127.0.0.1:9002"
WS_URL = f"ws://127.0.0.1:{WS_PORT}/api/v1/voice/ws"


def _env(k: str, default: str) -> str:
    return os.environ.get(k, default)


def _envelope(type_: str, body: dict) -> dict:
    return {
        "version": "2.0",
        "type": type_,
        "message_id": uuid.uuid4().hex,
        "timestamp": int(time.time()),
        "body": body,
    }


async def _recv_until(ws, pred, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("ws recv")
        data = await asyncio.wait_for(ws.recv(), timeout=left)
        env = json.loads(data)
        body = env.get("body") or env
        if env.get("type") == "voice.route_result" and pred(body):
            return body


async def _login_page():
    from app.infrastructure.drivers.browser import browser_manager

    page = await browser_manager.get_page()
    await page.goto(f"{BASE}/shop.html", wait_until="load", timeout=30000)
    await page.wait_for_timeout(1000)
    if "login" in page.url:
        await page.fill("[name='username']", _env("MALL_ADMIN_USER", "admin"))
        await page.fill("[name='password']", _env("MALL_ADMIN_PASS", "admin888"))
        await page.click("[lay-filter='login']")
        await page.wait_for_timeout(3000)
    assert "login" not in page.url, "商城登录失败"


STEPS = [
    {"label": "local: 截图", "text": "截图", "expected": "routed", "check_local": "screenshot"},
    {"label": "native macro: 关于微信", "text": "关于微信", "expected": "done"},
    {
        "label": "web read: 查价格",
        "text": "查一下夜光亚克力钥匙扣的价格",
        "expected": "done",
        "thread": "price-thread",
    },
    {
        "label": "anaphora: 它的库存",
        "text": "它的库存是多少",
        "expected": "done",
        "reuse": "price-thread",
    },
    {
        "label": "cache hit: 查价格2",
        "text": "查一下夜光亚克力钥匙扣的价格",
        "expected": "done",
    },
    {
        "label": "native bias: 飞书左侧",
        "text": "飞书左侧",
        "expected": "done",
    },
    {
        "label": "clarify: 查一下它的价格",
        "text": "查一下它的价格",
        "expected": "clarify",
        "thread": "clarify-thread",
    },
    {
        "label": "clarify-resume: 实体",
        "text": "夜光亚克力钥匙扣",
        "expected": "done",
        "reuse": "clarify-thread",
    },
]


async def main() -> None:
    import uvicorn
    import websockets

    from app.main import app

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=WS_PORT, log_level="error")
    )
    serve_task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.2)

    try:
        await _login_page()
        print("[e2e] 商城登录态 OK\n")

        async with websockets.connect(WS_URL) as ws:
            await ws.recv()  # system.init
            threads: dict[str, str] = {}
            results = []

            for i, step in enumerate(STEPS):
                if step.get("reuse"):
                    thread = step["reuse"]
                else:
                    thread = step.get("thread") or f"e2e-{i}"
                if step.get("thread") and step["thread"] not in threads:
                    threads[step["thread"]] = thread

                text = step["text"]
                try:
                    t0 = time.monotonic()
                    await ws.send(
                        json.dumps(_envelope("voice.route", {"thread_id": thread, "text": text}))
                    )
                    body = await _recv_until(
                        ws,
                        lambda b, t=thread: b.get("thread_id") == t and "status" in b,
                        120,
                    )
                    route_ms = (time.monotonic() - t0) * 1000

                    if body.get("status") == "routed" and body.get("target", {}).get("type") in (
                        "macro",
                        "skill",
                        "agent",
                    ):
                        body = await _recv_until(
                            ws,
                            lambda b, t=thread: b.get("thread_id") == t
                            and b.get("status") in ("done", "failed", "clarify"),
                            120,
                        )

                    ok = body.get("status") == step["expected"]
                    if step.get("check_local"):
                        ok = ok and body.get("target", {}).get("id") == step["check_local"]
                    if step.get("cache_hit"):
                        ok = ok and route_ms < 1000
                    status = body.get("status")
                except Exception as e:
                    ok = False
                    status = f"exception: {type(e).__name__}"
                    route_ms = 0

                results.append((step["label"], ok, status, route_ms))
                print(f"{'PASS' if ok else 'FAIL'} [{step['label']}] {text!r}")
                print(f"       status={status} ({route_ms:.0f}ms)")
                await asyncio.sleep(1.0)

            passed = sum(1 for _, ok, _, _ in results if ok)
            print(f"\n── 汇总 {passed}/{len(results)} ──")
            for label, ok, status, ms in results:
                print(f"  {'✓' if ok else '✗'} {label}: {status} ({ms:.0f}ms)")
    finally:
        server.should_exit = True
        await serve_task


if __name__ == "__main__":
    asyncio.run(main())
