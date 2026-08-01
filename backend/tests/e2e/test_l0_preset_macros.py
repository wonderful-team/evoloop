"""
E2E: preset macros + builtin commands + navigation macros via voice WS.

Requires the backend to be running on 127.0.0.1:20160
and seed_preset_macros.py / seed_navigation_macros.py to have been run.

Each test:
  1. Connects to WS
  2. Sends voice.route with a trigger phrase
  3. Verifies voice.route_result or voice.navigate response
  4. Measures round-trip timing
"""

import asyncio
import json
import sys
import time
import uuid

from websockets.client import connect

TIMEOUT = 30
BACKEND_URL = "ws://127.0.0.1:20160/api/v1/voice/ws"

passed = 0
failed = 0
elapsed_list = []


# ── Test matrix ───────────────────────────────────────────────

BUILTIN_TESTS = [
    # (name, text, expected_action)
    ("clearify", "再说一遍", "clarify"),
    ("end_1", "再见", "end"),
    ("end_2", "拜拜", "end"),
    ("end_3", "结束", "end"),
    ("rename", "你以后叫小爱", "rename"),
    ("ack_1", "对对对", "ack"),
    ("ack_2", "没错", "ack"),
    ("ack_3", "可以", "ack"),
    ("cancel_1", "算了", "cancel"),
    ("cancel_2", "取消", "cancel"),
]

PRESET_MACRO_TESTS = [
    # (name, text, expected_action_prefix)
    ("mute_1", "静音", "macro:"),
    ("mute_2", "别出声", "macro:"),
    ("mute_3", "帮我静音", "macro:"),  # prefix
    ("mute_4", "静音一下", "macro:"),  # suffix
    ("mute_5", "帮我静音一下", "macro:"),  # prefix + suffix
    ("unmute_1", "取消静音", "macro:"),
    ("unmute_2", "恢复声音", "macro:"),
    ("volume_up", "音量大一点", "macro:"),
    ("volume_down", "音量小一点", "macro:"),
    ("volume_max", "音量最大", "macro:"),
    ("play_pause_1", "暂停", "macro:"),
    ("play_pause_2", "继续", "macro:"),
    ("play_pause_3", "先停", "macro:"),
    ("next_track_1", "下一首", "macro:"),
    ("next_track_2", "切歌", "macro:"),
    ("prev_track_1", "上一首", "macro:"),
    ("prev_track_2", "回上一首", "macro:"),
    ("screenshot_1", "截图", "macro:"),
    ("screenshot_2", "截个图", "macro:"),
    ("lock_screen_1", "锁屏", "macro:"),
    ("lock_screen_2", "锁电脑", "macro:"),
    ("open_wechat", "打开微信", "macro:"),
    ("open_chrome", "打开Chrome", "macro:"),
    ("open_safari", "打开Safari", "macro:"),
    ("open_terminal", "打开终端", "macro:"),
    ("open_finder_1", "打开Finder", "macro:"),
    ("open_finder_2", "打开访达", "macro:"),
    ("open_vscode_1", "打开VS Code", "macro:"),
    ("open_vscode_2", "打开VSCode", "macro:"),
    ("quit_wechat", "退出微信", "macro:"),
    ("quit_chrome", "退出Chrome", "macro:"),
    ("quit_safari", "退出Safari", "macro:"),
    ("press_enter_1", "按回车", "macro:"),
    ("press_enter_2", "按下回车", "macro:"),
    ("press_space", "按空格", "macro:"),
]

# Navigation macros live in the DB macro table and produce a ``voice.navigate``
# event rather than a ``voice.route_result``. They are matched before BERT and
# are language-scoped by the backend's configured LANGUAGE (zh/en/etc.).
NAVIGATION_TESTS = [
    # (name, text, expected_route, expected_feedback_substring)
    ("nav_show_main_window_zh", "显示主窗口", "/chat", "主界面"),
]

NEGATIVE_TESTS = [
    # Utterances that MUST NOT trigger L0
    ("complex_query", "今天天气怎么样"),
    ("multi_intent", "打开微信给张三发消息"),
    ("context_needed", "我上个月买的耳机在哪里"),
]


async def run_scenario(scenario_id, _name, text, expect_prefix):
    """Run one scenario and return (passed, elapsed, detail)."""
    global passed, failed
    thread_id = f"l0-e2e-{scenario_id}-{uuid.uuid4().hex[:8]}"

    try:
        async with connect(BACKEND_URL, open_timeout=5) as ws:
            init_raw = await asyncio.wait_for(ws.recv(), timeout=5)
            init = json.loads(init_raw)
            assert init.get("type") == "system.init"

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
            t0 = time.time()

            await ws.send(json.dumps(route))

            status = ""
            action = ""
            has_result = False

            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                env = json.loads(raw)
                t = env.get("type", "?")
                b = env.get("body", {})
                s = b.get("status", "")
                target = b.get("target", {})
                act = target.get("action", "") if isinstance(target, dict) else ""
                summary = b.get("summary", "")

                if t == "voice.route_result":
                    has_result = True
                    status = s
                    action = act
                    elapsed = time.time() - t0
                    if s == "routed":
                        break
                    if s in ("done", "failed", "cancelled"):
                        break

            elapsed = time.time() - t0
            assert has_result, f"No voice.route_result received for '{text}'"

            if expect_prefix == "macro:":
                assert status == "done", (
                    f"'{text}': 期望 status=done, 得到 status={status}, summary={summary[:60]}"
                )
            elif expect_prefix in ("ack", "cancel", "end", "clarify", "rename"):
                assert action == expect_prefix or status in ("done", "cancelled"), (
                    f"'{text}': 期望 action={expect_prefix} 或 status=done, 得到 action={action}, status={status}"
                )

            passed += 1
            elapsed_list.append(elapsed)
            return (True, elapsed, f"OK ({elapsed * 1000:.0f}ms)")

    except asyncio.TimeoutError as e:
        failed += 1
        return (False, 0, f"timeout: {e}")
    except Exception as e:
        failed += 1
        return (False, 0, str(e) or e.__class__.__name__)


async def run_negative(scenario_id, _name, text):
    """Verify utterance does NOT trigger L0 (should go to Agent)."""
    global passed, failed
    thread_id = f"l0-neg-{scenario_id}-{uuid.uuid4().hex[:8]}"

    try:
        async with connect(BACKEND_URL, open_timeout=5) as ws:
            init_raw = await asyncio.wait_for(ws.recv(), timeout=5)
            init = json.loads(init_raw)
            assert init.get("type") == "system.init"

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

            saw_routed_local = False
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                except asyncio.TimeoutError:
                    break  # No response within 3s = correctly delegated to Agent
                env = json.loads(raw)
                b = env.get("body", {})
                s = b.get("status", "")
                target = b.get("target", {})
                tt = target.get("type") if isinstance(target, dict) else ""

                if s == "routed" and tt == "local":
                    saw_routed_local = True
                    break
                if s in ("routed", "done", "failed"):
                    break  # agent or error — not L0

            assert not saw_routed_local, f"'{text}' 不应触发 L0 (got routed/local)"
            passed += 1
            return (True, 0, "OK (delegated to agent)")

    except asyncio.TimeoutError as e:
        failed += 1
        return (False, 0, f"timeout: {e}")
    except Exception as e:
        failed += 1
        return (False, 0, str(e) or e.__class__.__name__)


async def run_navigation_scenario(
    scenario_id, _name, text, expected_route, expected_feedback
):
    """Run one navigation macro scenario and return (passed, elapsed, detail)."""
    global passed, failed
    thread_id = f"l0-nav-{scenario_id}-{uuid.uuid4().hex[:8]}"

    try:
        async with connect(BACKEND_URL, open_timeout=5) as ws:
            init_raw = await asyncio.wait_for(ws.recv(), timeout=5)
            init = json.loads(init_raw)
            assert init.get("type") == "system.init"

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
            t0 = time.time()
            await ws.send(json.dumps(route))

            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                env = json.loads(raw)
                t = env.get("type", "?")
                b = env.get("body", {})

                if t == "voice.navigate":
                    actual_route = b.get("route", "")
                    actual_feedback = b.get("feedback", "")
                    assert actual_route == expected_route, (
                        f"'{text}': 期望 route={expected_route}, 得到 route={actual_route}"
                    )
                    assert expected_feedback.lower() in actual_feedback.lower(), (
                        f"'{text}': feedback 不包含 '{expected_feedback}', 得到 feedback={actual_feedback}"
                    )
                    elapsed = time.time() - t0
                    passed += 1
                    elapsed_list.append(elapsed)
                    return (True, elapsed, f"OK ({elapsed * 1000:.0f}ms)")

                # Safety: stop if we get a terminal route_result without seeing navigate.
                if t == "voice.route_result" and b.get("status") in (
                    "done",
                    "failed",
                    "cancelled",
                ):
                    raise AssertionError(
                        f"'{text}': navigation macro 返回了普通 macro 结果，未收到 voice.navigate"
                    )

    except asyncio.TimeoutError as e:
        failed += 1
        return (False, 0, f"timeout: {e}")
    except Exception as e:
        failed += 1
        return (False, 0, str(e) or e.__class__.__name__)


async def main():
    global passed, failed
    print(f"\n{'=' * 60}")
    print("L0 预置 Macro + 内置命令 E2E 测试")
    print(f"{'=' * 60}")
    print(f"后端: {BACKEND_URL}")
    print()

    series = [
        ("内置命令", BUILTIN_TESTS, True),
        ("预置 Macro", PRESET_MACRO_TESTS, True),
        ("导航 Macro", NAVIGATION_TESTS, True),
        ("否定用例（不应命中）", NEGATIVE_TESTS, False),
    ]

    for title, tests, is_positive in series:
        print(f"\n── {title} ──")
        for i, test in enumerate(tests):
            if title == "导航 Macro":
                name, text, expected_route, expected_feedback = test
                ok, elapsed, detail = await run_navigation_scenario(
                    i, name, text, expected_route, expected_feedback
                )
            elif is_positive:
                name, text, expect = test
                ok, elapsed, detail = await run_scenario(i, name, text, expect)
            else:
                name, text = test
                ok, elapsed, detail = await run_negative(i, name, text)
            icon = "✅" if ok else "❌"
            print(f"  {icon} [{name:25s}] {text:15s} → {detail}")

    print(f"\n{'=' * 60}")
    print(f"结果: {passed} 通过, {failed} 失败 / {passed + failed} 总计")
    if elapsed_list:
        avg_ms = sum(elapsed_list) / len(elapsed_list) * 1000
        max_ms = max(elapsed_list) * 1000
        min_ms = min(elapsed_list) * 1000
        print(f"平均耗时: {avg_ms:.0f}ms, 最快: {min_ms:.0f}ms, 最慢: {max_ms:.0f}ms")
    print(f"{'=' * 60}\n")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
