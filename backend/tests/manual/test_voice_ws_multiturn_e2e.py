"""Voice WebSocket full-link multi-turn E2E: real uvicorn server + real
voice_ws protocol + real macro execution against the live mall admin.

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=xxx \
        .venv/bin/python tests/manual/test_voice_ws_multiturn_e2e.py

Server and client share ONE asyncio loop (uvicorn.Server as a task), so the
lazily-started browser lives in the same loop as both the macro engine and
the pre-login — no cross-loop playwright conflict.

Turns over the wire (canonical envelopes, ws://127.0.0.1:8123/api/v1/ws):
  thread ws-mt:
    1. "打开商品列表"            -> route_result routed #110 -> result done
    2. "查一下夜光亚克力钥匙扣的价格" -> routed #107 -> done (real extraction)
    3. "把它的库存改成142"       -> anaphora rewrite -> routed #54 -> money
       HITL (executor._run_agent patched to capture + push status "hitl")
  thread ws-clarify:
    4. "把它的库存改成142"       -> route_result status=clarify (no execution)
    5. "夜光亚克力钥匙扣"        -> clarify resume -> routed #54 -> hitl
"""

import asyncio
import os
import sys
import time
import uuid

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

BASE = "http://127.0.0.1:9002"
WS_PORT = 8123


def _envelope(mtype: str, body: dict) -> dict:
    return {
        "version": "2.0",
        "type": mtype,
        "message_id": str(uuid.uuid4()),
        "timestamp": int(time.time()),
        "body": body,
    }


async def _recv_until(ws, pred, timeout: float, label: str) -> dict:
    """Read envelopes until pred(body) holds; returns the matching body."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        left = deadline - loop.time()
        if left <= 0:
            raise TimeoutError(f"等待超时: {label}")
        data = await asyncio.wait_for(ws.recv(), timeout=left)
        import json as _json

        env = _json.loads(data)
        if env.get("type") != "voice.route_result":
            continue
        body = env.get("body") or {}
        if pred(body):
            return body


async def main() -> None:
    import uvicorn
    import websockets

    from app.core.routing import executor
    from app.infrastructure.drivers.browser import browser_manager

    # Patch BEFORE any request: money HITL delegate is captured, not executed.
    delegated = []
    orig_run_agent = executor._run_agent

    async def capture_agent(*a, **kw):
        delegated.append(kw)
        meta = kw.get("metadata") or {}
        await executor.push_voice_result(
            kw.get("voice_thread_id") or (meta or {}).get("voice_thread_id") or a[0],
            "hitl",
            f"宏{meta.get('macro_id')} 待人工确认",
        )

    executor._run_agent = capture_agent

    from app.main import app

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=WS_PORT, log_level="error")
    )
    serve_task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.2)

    failures = []
    try:
        # Pre-login in the SAME loop the engine will use.
        page = await browser_manager.get_page()
        await page.goto(f"{BASE}/shop.html", wait_until="load", timeout=30000)
        await page.wait_for_timeout(1500)
        if "login" in page.url:
            await page.fill("[name='username']", os.environ["MALL_ADMIN_USER"])
            await page.fill("[name='password']", os.environ["MALL_ADMIN_PASS"])
            await page.click("[lay-filter='login']")
            await page.wait_for_timeout(3000)
        assert "login" not in page.url, "登录失败"
        print("[e2e] 登录态 OK（与引擎同 loop）")

        async with websockets.connect(f"ws://127.0.0.1:{WS_PORT}/api/v1/voice/ws") as ws:
            await ws.recv()  # system.init

            async def turn(thread: str, text: str):
                print(f"\n===== TURN [{thread}]: {text} =====")
                await ws.send(
                    __import__("json").dumps(
                        _envelope("voice.route", {"thread_id": thread, "text": text})
                    )
                )
                decision = await _recv_until(
                    ws,
                    lambda b: b.get("thread_id") == thread and "status" in b,
                    timeout=60,
                    label=f"route_result: {text}",
                )
                print(f"  <- status={decision.get('status')} target={decision.get('target')} params={decision.get('params')}")
                return decision

            async def wait_result(thread: str, timeout: float = 90):
                result = await _recv_until(
                    ws,
                    lambda b: b.get("thread_id") == thread and "summary" in b,
                    timeout=timeout,
                    label=f"voice_result[{thread}]",
                )
                print(f"  <- result status={result.get('status')} summary={str(result.get('summary'))[:80]}")
                return result

            # ── 1: 打开商品列表 ─────────────────────────────────
            d = await turn("ws-mt", "打开商品列表")
            if (d.get("target") or {}).get("id") != 110:
                failures.append(f"T1 未路由宏110: {d}")
            r = await wait_result("ws-mt")
            if r.get("status") != "done":
                failures.append(f"T1 执行未 done: {r}")

            # ── 2: 真查价 ──────────────────────────────────────
            d = await turn("ws-mt", "查一下夜光亚克力钥匙扣的价格")
            if (d.get("target") or {}).get("id") != 107:
                failures.append(f"T2 未路由宏107: {d}")
            r = await wait_result("ws-mt")
            if r.get("status") != "done":
                failures.append(f"T2 执行未 done: {r}")

            # ── 3: 指代改库存 → money HITL ──────────────────────
            delegated.clear()
            d = await turn("ws-mt", "把它的库存改成142")
            if (d.get("target") or {}).get("id") != 54 or (d.get("params") or {}).get("query") != "夜光亚克力钥匙扣":
                failures.append(f"T3 指代改写/路由异常: {d}")
            r = await wait_result("ws-mt")
            if r.get("status") != "hitl" or not delegated or delegated[0]["metadata"].get("macro_id") != 54:
                failures.append(f"T3 money HITL 未按预期: result={r} delegated={delegated}")

            # ── 4: 新对话冷指代 → clarify ───────────────────────
            d = await turn("ws-clarify", "把它的库存改成142")
            if d.get("status") != "clarify" or "哪个商品" not in str((d.get("params") or {}).get("question", "")):
                failures.append(f"T4 应 clarify: {d}")

            # ── 5: 作答 → 合成 → 宏54 HITL ─────────────────────
            delegated.clear()
            d = await turn("ws-clarify", "夜光亚克力钥匙扣")
            if (d.get("target") or {}).get("id") != 54:
                failures.append(f"T5 clarify 续接后未路由宏54: {d}")
            r = await wait_result("ws-clarify")
            if r.get("status") != "hitl" or not delegated or delegated[0]["metadata"].get("macro_id") != 54:
                failures.append(f"T5 money HITL 未按预期: result={r} delegated={delegated}")
    finally:
        executor._run_agent = orig_run_agent
        server.should_exit = True
        await serve_task

    print("\n" + ("=" * 40))
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        sys.exit(1)
    print("VOICE-WS MULTI-TURN PASS")


if __name__ == "__main__":
    asyncio.run(main())
