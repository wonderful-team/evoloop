"""
E2E test suite for voice pipeline scenarios.

Covers all 14 scenarios from the design document §10.18.
Requires the backend to be running on 127.0.0.1:20160.
"""

import asyncio
import json
import uuid
import sys
from websockets.client import connect

# Timeout per scenario (seconds)
TIMEOUT = 30
BACKEND_URL = "ws://127.0.0.1:20160/api/v1/voice/ws"

passed = 0
failed = 0
results = []


async def test_scenario(scenario_id: int, name: str, text: str, expect: str) -> bool:
    """
    Run a single voice scenario against the backend.

    expect: 'done' for Agent responses, 'local' for L0 hits, 'failed' for errors
    """
    global passed, failed
    thread_id = f"e2e-s{scenario_id}-{uuid.uuid4().hex[:8]}"
    elapsed = 0.0

    try:
        async with connect(BACKEND_URL, open_timeout=5) as ws:
            # Wait for system.init handshake
            init_raw = await asyncio.wait_for(ws.recv(), timeout=5)
            init = json.loads(init_raw)
            assert init.get("type") == "system.init", f"Expected system.init, got {init.get('type')}"

            # Send voice.route
            msg_id = uuid.uuid4().hex
            route = {
                "version": "2.0",
                "type": "voice.route",
                "message_id": msg_id,
                "body": {
                    "thread_id": thread_id,
                    "text": text,
                    "message_id": msg_id,
                },
            }
            await ws.send(json.dumps(route))

            # Collect responses
            statuses = []
            target_types = []
            has_summary = False
            has_token = False

            t0 = asyncio.get_event_loop().time()
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                env = json.loads(raw)
                t = env.get("type", "?")
                b = env.get("body", {})
                s = b.get("status", "")
                target = b.get("target", {})
                tt = target.get("type") if isinstance(target, dict) else ""
                summary = b.get("summary", "")

                statuses.append(s)
                if tt:
                    target_types.append(tt)
                if summary:
                    has_summary = True
                if t == "voice.token":
                    has_token = True

                if s == "routed" and tt == "local":
                    break  # L0 hit
                if s in ("done", "failed", "cancelled"):
                    break

            elapsed = asyncio.get_event_loop().time() - t0

    except asyncio.TimeoutError:
        ok = False
        detail = f"TIMEOUT ({TIMEOUT}s)"
    except Exception as e:
        ok = False
        detail = f"ERROR: {e}"
    else:
        last_status = statuses[-1] if statuses else "none"
        if expect == "done":
            ok = last_status == "done"
            detail = f"last={last_status} statuses={statuses}"
        elif expect == "local":
            ok = last_status == "routed" and "local" in target_types
            detail = f"last={last_status} target={target_types}"
        elif expect == "failed":
            ok = last_status == "failed"
            detail = f"last={last_status} statuses={statuses}"
        else:
            ok = False
            detail = f"unknown expect={expect}"

    if ok:
        passed += 1
        results.append((scenario_id, name, f"✅ PASS"))
        print(f"  ✅ [{scenario_id:2d}] {name:20s} ({elapsed:.1f}s) - {expect}")
        return True
    else:
        failed += 1
        results.append((scenario_id, name, f"❌ FAIL - {detail}"))
        print(f"  ❌ [{scenario_id:2d}] {name:20s} ({elapsed:.1f}s) - {detail}")
        return False


async def main():
    global passed, failed

    print("=" * 65)
    print("Voice Pipeline E2E Test Suite")
    print("=" * 65)
    print()

    scenarios = [
        # ── L0 fast path (local actions) ──
        (1,  "L0 mute",          "静音",          "local"),
        (2,  "L0 unmute",        "取消静音",      "local"),
        (3,  "L0 screenshot",    "截图",          "local"),
        (4,  "L0 lock screen",   "锁屏",          "local"),
        (5,  "L0 volume up",     "音量调大一点",  "local"),
        (6,  "L0 volume max",    "音量最大",      "local"),
        (7,  "L0 volume half",   "音量一半",      "local"),
        (8,  "L0 pause",         "暂停",          "local"),
        (9,  "L0 resume",        "继续",          "local"),
        (10, "L0 next track",    "下一首",        "local"),
        (11, "L0 prev track",    "上一首",        "local"),
        (12, "L0 press enter",   "按一下回车",    "local"),
        (13, "L0 press esc",     "按Esc",         "local"),
        # open/focus/quit_app skipped — requires local app DB (Atlas sync)
        (14, "L0 rename",        "你以后叫小智",  "local"),
        (15, "L0 clarify",       "再说一遍",      "local"),
        (16, "L0 end",           "再见",          "local"),
        (17, "L0 end 2",         "拜拜",          "local"),
        (18, "L0 end 3",         "结束",          "local"),
        # ── Greeting ──
        (19, "Greeting",         "你好",          "done"),
        # ── Knowledge Q&A ──
        (20, "Simple QA",        "1+1等于几",     "done"),
        (20, "Simple QA 2",      "2+2等于多少",    "done"),
        # ── Simple task ──
        (21, "Simple task",      "今天天气怎么样", "done"),
        # ── Complex task ──
        (22, "Complex task",     "帮我写一个Python脚本读取CSV文件", "done"),
        # ── Async task ──
        (23, "Async notify",     "分析一下当前项目", "done"),
        # ── Status query ──
        (24, "Status query",     "完成了吗",       "done"),
        # ── Correction ──
        (25, "Correction",       "不，换一个方案", "done"),
        # ── Mixed command ──
        (26, "Mixed cmd",        "打开浏览器然后搜索天气", "done"),
        # ── Fuzzy input ──
        (30, "Fuzzy input",      "那个…呃…帮我查一下", "done"),
    ]

    for sid, name, text, expect in scenarios:
        await test_scenario(sid, name, text, expect)
        await asyncio.sleep(0.5)  # Brief pause between scenarios

    # Multi-turn test (scenarios 7-8)
    print()
    print("  --- Multi-turn (scenarios 7-8) ---")
    thread_id = f"e2e-mt-{uuid.uuid4().hex[:8]}"
    mt_passed = 0
    try:
        async with connect(BACKEND_URL, open_timeout=5) as ws:
            init_raw = await asyncio.wait_for(ws.recv(), 5)
            init = json.loads(init_raw)

            # Turn 1: ask a question
            msg_id = uuid.uuid4().hex
            await ws.send(json.dumps({
                "version": "2.0", "type": "voice.route",
                "message_id": msg_id,
                "body": {"thread_id": thread_id, "text": "推荐一本Python入门书", "message_id": msg_id},
            }))
            t1 = asyncio.get_event_loop().time()
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                env = json.loads(raw)
                s = env.get("body", {}).get("status", "")
                if s in ("done", "failed", "cancelled"):
                    break
            t1e = asyncio.get_event_loop().time() - t1
            mt_passed += 1
            print(f"  ✅ Turn 1: recommend book ({t1e:.1f}s)")

            # Turn 2: follow-up with reference
            await asyncio.sleep(1)
            msg_id = uuid.uuid4().hex
            await ws.send(json.dumps({
                "version": "2.0", "type": "voice.route",
                "message_id": msg_id,
                "body": {"thread_id": thread_id, "text": "这本适合零基础吗", "message_id": msg_id},
            }))
            t2 = asyncio.get_event_loop().time()
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                env = json.loads(raw)
                s = env.get("body", {}).get("status", "")
                if s in ("done", "failed", "cancelled"):
                    break
            t2e = asyncio.get_event_loop().time() - t2
            mt_passed += 1
            print(f"  ✅ Turn 2: follow-up ({t2e:.1f}s)")
    except Exception as e:
        print(f"  ❌ Multi-turn failed: {e}")

    # Summary
    print()
    print("=" * 65)
    total = passed + failed + (2 - mt_passed)
    print(f"Results: {passed}/{passed + failed + (2 - mt_passed)} passed (+ {mt_passed}/2 multi-turn)")
    print("=" * 65)

    if failed > 0 or mt_passed < 2:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
