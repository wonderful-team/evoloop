"""大规模真实全链路 E2E：找出系统级实问题。

目标：用真实 uvicorn+websocket+浏览器+原生应用，跑大量多样用例，
暴露并发/状态/缓存/澄清/指代/路由偏置等真实缺陷。

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=admin888 \\
        .venv/bin/python tests/manual/voice_chain_real_exhaustive.py

每用例独立 try/except；失败不阻断；最后出汇总+失败明细。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

WS_PORT = 18314
BASE = "http://127.0.0.1:9002"
WS_URL = f"ws://127.0.0.1:{WS_PORT}/api/v1/voice/ws"


def _env(k, d=""):
    return os.environ.get(k, d)


def _env_body(type_, body):
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
        body = env.get("body") or env
        if env.get("type") == "voice.route_result" and pred(body):
            return body


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
    assert "login" not in page.url, "login failed"


async def _reset_shop():
    from app.infrastructure.drivers.browser import browser_manager

    try:
        page = await browser_manager.get_page()
        await page.goto(f"{BASE}/shop.html", wait_until="load", timeout=30000)
        await page.wait_for_timeout(800)
    except Exception as e:
        print(f"[warn] reset shop failed: {e}")


CASES = [
    # L0 本地动作（只验证路由结果，不执行本地动作）
    {"label": "L0: 截图", "text": "截图", "expect": "routed", "target_type": "local", "target_id": "screenshot"},
    {"label": "L0: 静音", "text": "静音", "expect": "routed", "target_type": "local", "target_id": "mute"},
    {"label": "L0: 取消静音", "text": "取消静音", "expect": "routed", "target_type": "local", "target_id": "unmute"},
    {"label": "L0: 音量大一点", "text": "音量大一点", "expect": "routed", "target_type": "local", "target_id": "set_volume"},
    {"label": "L0: 暂停", "text": "暂停", "expect": "routed", "target_type": "local", "target_id": "play_pause"},
    {"label": "L0: 下一首", "text": "下一首", "expect": "routed", "target_type": "local", "target_id": "next_track"},
    {"label": "L0: 锁屏", "text": "锁屏", "expect": "routed", "target_type": "local", "target_id": "lock_screen"},
    {"label": "L0: 打开微信", "text": "打开微信", "expect": "routed", "target_type": "local", "target_id": "open_app"},
    # Web 读宏
    {"label": "web: 查价格", "text": "查一下夜光亚克力钥匙扣的价格", "expect": "done", "reset": True},
    {"label": "web: 查库存", "text": "查一下夜光亚克力钥匙扣的库存", "expect": "done", "reset": True},
    {"label": "web: 查售价", "text": "查一下夜光亚克力钥匙扣的售价", "expect": "done", "reset": True},
    {"label": "web: 查订单", "text": "打开订单列表", "expect": "done", "reset": True},
    # Native 宏（全部 harmless）
    {"label": "native: 关于微信", "text": "关于微信", "expect": "done"},
    {"label": "native: 关于飞书", "text": "关于飞书", "expect": "done"},
    {"label": "native: Chrome 新标签页", "text": "新标签页", "expect": "done"},
    {"label": "native: Lark 左侧", "text": "飞书左侧", "expect": "done"},
    {"label": "native: WeChat 放大", "text": "微信放大", "expect": "done"},
    {"label": "native: iTerm New Tab", "text": "New Tab", "expect": "done"},
    # 多意图
    {"label": "multi: 价格和库存", "text": "查一下夜光亚克力钥匙扣的价格和库存", "expect": "done", "intents_min": 2, "reset": True},
    {"label": "multi: 两个 native 无关", "text": "关于微信然后关于飞书", "expect": "done", "intents_min": 2},
    # 指代（同线程）
    {"label": "anaphora: 查价格", "text": "查一下夜光亚克力钥匙扣的价格", "expect": "done", "thread": "ana-thread", "reset": True},
    {"label": "anaphora: 它的库存", "text": "它的库存是多少", "expect": "done", "reuse": "ana-thread"},
    {"label": "anaphora: 这个售价", "text": "这个售价是多少", "expect": "done", "reuse": "ana-thread"},
    # 澄清
    {"label": "clarify: 查它的价格", "text": "查一下它的价格", "expect": "clarify", "thread": "clarify-thread"},
    {"label": "clarify-resume", "text": "夜光亚克力钥匙扣", "expect": "done", "reuse": "clarify-thread"},
    # 路由缓存（两次重复，第二次应明显更快）
    {"label": "cache: 查价格", "text": "查一下夜光亚克力钥匙扣的价格", "expect": "done", "thread": "cache-thread", "reset": True},
    {"label": "cache-hit: 查价格", "text": "查一下夜光亚克力钥匙扣的价格", "expect": "done", "reuse": "cache-thread", "cache_fast": True},
    # 未知/兜底
    {"label": "unknown: 天王盖地虎", "text": "天王盖地虎", "expect": "any", "allow": ["done", "failed", "clarify"]},
]


async def _run_case(ws, step, threads):
    if step.get("reuse"):
        thread = step["reuse"]
    else:
        thread = step.get("thread") or f"real-{uuid.uuid4().hex[:6]}"
    if step.get("thread") and step["thread"] not in threads:
        threads[step["thread"]] = thread

    if step.get("reset"):
        await _reset_shop()
        await asyncio.sleep(0.5)

    text = step["text"]
    t0 = time.monotonic()
    await ws.send(json.dumps(_env_body("voice.route", {"thread_id": thread, "text": text})))
    body = await _recv(ws, lambda b, t=thread: b.get("thread_id") == t and "status" in b, 120)
    route_ms = (time.monotonic() - t0) * 1000

    if body.get("status") == "routed" and body.get("target", {}).get("type") in ("macro", "skill", "agent"):
        body = await _recv(ws, lambda b, t=thread: b.get("thread_id") == t and b.get("status") in ("done", "failed", "clarify"), 120)

    return body, route_ms


async def _check(step, body, route_ms):
    if step.get("expect") == "any":
        return body.get("status") in step.get("allow", [])
    if body.get("status") != step["expect"]:
        return False
    if step.get("target_type") and body.get("target", {}).get("type") != step["target_type"]:
        return False
    if step.get("target_id") and body.get("target", {}).get("id") != step["target_id"]:
        return False
    if step.get("intents_min") and body.get("intents", 1) < step["intents_min"]:
        return False
    if step.get("cache_fast") and route_ms >= 1000:
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
        print("[real-e2e] 商城登录态 OK\n")

        async with websockets.connect(WS_URL) as ws:
            await ws.recv()  # system.init
            threads = {}
            results = []
            for step in CASES:
                try:
                    body, route_ms = await _run_case(ws, step, threads)
                    ok = await _check(step, body, route_ms)
                    status = body.get("status")
                    detail = f"target={body.get('target')} intents={body.get('intents')}"
                except Exception as e:
                    ok = False
                    status = f"exception:{type(e).__name__}"
                    detail = str(e)
                    route_ms = 0
                results.append((step["label"], ok, status, route_ms, detail))
                print(f"{'PASS' if ok else 'FAIL'} [{step['label']}] {step['text']!r}")
                print(f"       {status} ({route_ms:.0f}ms) {detail}")
                await asyncio.sleep(1.0)

            passed = sum(1 for _, ok, _, _, _ in results if ok)
            total = len(results)
            print(f"\n── 汇总 {passed}/{total} ──")
            for label, ok, status, ms, detail in results:
                print(f"  {'✓' if ok else '✗'} {label}: {status} ({ms:.0f}ms) {detail}")
            if passed != total:
                print("\n── 失败明细 ──")
                for label, ok, status, ms, detail in results:
                    if not ok:
                        print(f"  {label}: {status} ({ms:.0f}ms) {detail}")
    finally:
        server.should_exit = True
        await task


if __name__ == "__main__":
    asyncio.run(main())
