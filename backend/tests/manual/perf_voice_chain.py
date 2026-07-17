"""Full voice-chain latency profile (Agent path excluded):

    ASR (measured separately, see report §39) -> [this script]
    text -> ws route decision (decompose gate/retrieve/route LLM) -> macro
    execution in real browser -> result.

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=admin888 \
        .venv/bin/python tests/manual/perf_voice_chain.py
"""

import asyncio
import json
import os
import sys
import time
import uuid

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

WS_PORT = 18311
BASE = "http://127.0.0.1:9002"
WS_URL = f"ws://127.0.0.1:{WS_PORT}/api/v1/voice/ws"

COMMANDS = [
    "打开商品列表",
    "查一下夜光亚克力钥匙扣的价格",
    "查一下夜光亚克力钥匙扣的库存",
    "打开订单列表",
]


def _envelope(type_: str, body: dict) -> dict:
    return {
        "version": "2.0",
        "type": type_,
        "message_id": uuid.uuid4().hex,
        "timestamp": int(time.time()),
        "body": body,
    }


async def _recv_until(ws, pred, timeout: float, label: str) -> tuple[dict, float]:
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError(label)
        data = await asyncio.wait_for(ws.recv(), timeout=left)
        env = json.loads(data)
        body = env.get("body") or env
        if env.get("type") != "voice.route_result":
            continue
        if pred(body):
            return body, time.monotonic()


async def main() -> None:
    import uvicorn
    import websockets

    from app.core.routing import executor  # noqa: F401  (ensure routing wired)
    from app.infrastructure.drivers.browser import browser_manager
    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=WS_PORT, log_level="error"))
    serve_task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.2)

    try:
        page = await browser_manager.get_page()
        await page.goto(f"{BASE}/shop.html", wait_until="load", timeout=30000)
        await page.wait_for_timeout(1500)
        if "login" in page.url:
            await page.fill("[name='username']", os.environ["MALL_ADMIN_USER"])
            await page.fill("[name='password']", os.environ["MALL_ADMIN_PASS"])
            await page.click("[lay-filter='login']")
            await page.wait_for_timeout(3000)
        assert "login" not in page.url, "登录失败"
        print("[perf] 商城登录态 OK")

        rows = []
        async with websockets.connect(WS_URL) as ws:
            await ws.recv()  # system.init
            # each command twice: first = cache miss (LLM), second = cache hit
            for i, text in enumerate(COMMANDS):
                for attempt in (1, 2):
                    thread = f"perf-{i}-{attempt}"
                    t0 = time.monotonic()
                    await ws.send(json.dumps(_envelope("voice.route", {"thread_id": thread, "text": text})))
                    decision, t_dec = await _recv_until(
                        ws, lambda b, t=thread: b.get("thread_id") == t and "status" in b, 120, f"decision[{text}]"
                    )
                    route_ms = (t_dec - t0) * 1000
                    status = decision.get("status")
                    exec_ms = None
                    if (decision.get("target") or {}).get("id"):
                        _result, t_res = await _recv_until(
                            ws, lambda b, t=thread: b.get("thread_id") == t and "summary" in b, 120, f"result[{text}]"
                        )
                        exec_ms = (t_res - t_dec) * 1000
                        status = _result.get("status")
                    total_ms = (time.monotonic() - t0) * 1000
                    tag = "miss" if attempt == 1 else "HIT "
                    rows.append((text, route_ms, exec_ms, total_ms, status))
                    print(
                        f"  [{tag}] {text[:22]:24} 路由 {route_ms:8.0f} ms | 执行 "
                        f"{(f'{exec_ms:8.0f} ms' if exec_ms is not None else '   —   ')} | 全程 {total_ms:8.0f} ms | {status}"
                    )
                    await asyncio.sleep(0.3)

        warm = rows[1:] if len(rows) > 1 else rows
        avg_route = sum(r[1] for r in warm) / len(warm)
        execs = [r[2] for r in warm if r[2] is not None]
        avg_exec = sum(execs) / len(execs) if execs else 0
        avg_total = sum(r[3] for r in warm) / len(warm)
        print(f"\n[perf] 暖态均值（剔除首轮）: 路由 {avg_route:.0f} ms | 宏执行 {avg_exec:.0f} ms | 全程 {avg_total:.0f} ms")
    finally:
        server.should_exit = True
        await serve_task


if __name__ == "__main__":
    asyncio.run(main())
