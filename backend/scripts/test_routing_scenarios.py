#!/usr/bin/env python3
"""EvoLoop 消息链路全维度端到端测试（完整矩阵版）

维度 A - device_key：空、有效在线、有效离线、无效、其他用户
维度 B - project_id：空(0/全局)、有效(121)、无效(99999)
维度 C - 设备状态：在线、离线

覆盖场景：
  1.  A=空                          → HTTP 400 device_key required
  2.  A=无效                        → HTTP 403 device not found
  3.  A=他人设备                    → HTTP 403 device not belongs to you
  4A. A=在线 + B=全局(0) + 普通问题  → HTTP 200, AI 正常回复
  4B. A=在线 + B=全局(0) + 项目工具  → HTTP 200, AI 提示全局模式限制
  5.  A=在线 + B=有效(121)          → HTTP 200, AI 在项目上下文中回复
  6.  A=在线 + B=无效(99999)        → HTTP 200, Agent 报错或降级回复
  7A. A=离线 + B=全局(0)            → HTTP 202 device offline, command queued
  7B. A=离线 + B=有效(121)          → HTTP 202 device offline, command queued
  7C. A=离线 + B=无效(99999)        → HTTP 202 device offline, command queued
"""

import time
import os
import subprocess
import json
import requests

GATEWAY_URL = "http://127.0.0.1:9001"
MC_URL      = "http://127.0.0.1:9002"
USERNAME    = "preterchan"
PASSWORD    = "hellomylife"
LOCAL_SQLITE_DB = os.path.expanduser("~/.evoloop/database/backend.db")

# 伪造的 Redis 设备 key（测试结束后清除）
FAKE_OTHER_DEVICE_KEY   = "evo_test_other_member_device_001"   # 属于 member_id=2
FAKE_OFFLINE_DEVICE_KEY = "evo_test_offline_device_001"        # 属于 member_id=1，状态 offline

FAKE_OTHER_DEVICE_JSON = json.dumps({
    "device_key": FAKE_OTHER_DEVICE_KEY,
    "device_name": "TestUser2Device",
    "device_type": "desktop",
    "status": "online",
    "member_id": 2,
    "os_info": "TestOS/mock",
    "client_id": "test_client_for_scenario5",
    "last_ping_at": "2026-07-03T09:00:00+08:00",
    "connected_at": "2026-07-03T09:00:00+08:00",
})

FAKE_OFFLINE_DEVICE_JSON = json.dumps({
    "device_key": FAKE_OFFLINE_DEVICE_KEY,
    "device_name": "OfflineDesktopMock",
    "device_type": "desktop",
    "status": "offline",
    "member_id": 1,
    "os_info": "TestOS/mock",
    "client_id": "test_client_offline_mock",
    "last_ping_at": "2026-07-01T10:00:00+08:00",
    "connected_at": "2026-07-01T10:00:00+08:00",
})


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


# ─────────────────── Redis 操作 ───────────────────

def redis_set(key: str, value: str, ex: int = 3600) -> bool:
    res = subprocess.run(
        ["redis-cli", "SET", key, value, "EX", str(ex)],
        capture_output=True, text=True
    )
    return res.returncode == 0 and "OK" in res.stdout


def redis_del(*keys: str):
    subprocess.run(["redis-cli", "DEL"] + list(keys), capture_output=True)


# ─────────────────── SQLite 查询 ───────────────────

def run_sqlite_query(sql: str) -> list[str]:
    res = subprocess.run(["sqlite3", LOCAL_SQLITE_DB, sql],
                         capture_output=True, text=True)
    if res.returncode != 0:
        return []
    return [l for l in res.stdout.strip().splitlines() if l.strip()]


def wait_for_ai_response(thread_id: str, timeout: int = 40) -> str:
    """轮询本地 SQLite，等待 AI 角色的非空、非 audit 消息出现."""
    log(f"  ⏳ Polling SQLite for AI response in thread {thread_id}...")
    start = time.time()
    while time.time() - start < timeout:
        sql = (
            f"SELECT content FROM messages "
            f"WHERE thread_id = '{thread_id}' AND role = 'ai' "
            f"AND content != '' AND content IS NOT NULL "
            f"ORDER BY created_at DESC LIMIT 1;"
        )
        rows = run_sqlite_query(sql)
        if rows:
            content = rows[0].strip()
            if content and not content.startswith("<evoloop_session_audit"):
                return content
        time.sleep(2)
    return ""


# ─────────────────── 认证 / 设备 ───────────────────

def login() -> str:
    log("🔐 Login...")
    r = requests.post(f"{MC_URL}/api/login/login",
                      json={"username": USERNAME, "password": PASSWORD}, timeout=10)
    r.raise_for_status()
    token = r.json().get("data", {}).get("token")
    if not token:
        raise RuntimeError(f"Login failed: {r.text}")
    log(f"  ✅ Token acquired")
    return token


def get_online_device(token: str) -> str:
    r = requests.get(f"{GATEWAY_URL}/api/v1/devices",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    devices = r.json().get("data", {}).get("devices") or []
    for d in devices:
        if d.get("status") == "online":
            log(f"  ✅ Online device: {d['device_name']} ({d['device_key']})")
            return d["device_key"]
    if devices:
        log(f"  ⚠️  No online device, using: {devices[0]['device_name']}")
        return devices[0]["device_key"]
    raise RuntimeError("No registered devices found")


def send_cmd(token: str, payload: dict) -> requests.Response:
    return requests.post(
        f"{GATEWAY_URL}/api/v1/command/send",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )


# ─────────────────── 主测试逻辑 ───────────────────

def run_tests(token: str, online_device_key: str) -> list[tuple]:
    results = []

    def record(name, ok, detail):
        icon = "✅ PASSED" if ok else "❌ FAILED"
        print(f"  [{icon}] {name}")
        print(f"          {detail}\n")
        results.append((name, ok, detail))

    # ── Scenario 1: A=空 ──────────────────────────────────────────────────────
    log("\n══ Scenario 1: A=空 device_key ══")
    t1 = f"s1-nodev-{int(time.time())}"
    r = send_cmd(token, {"command_type": "chat", "thread_id": t1, "content": {"text": "hello"}})
    log(f"  HTTP {r.status_code}: {r.text[:80]}")
    ok = r.status_code == 400 and "device_key required" in r.text
    record("1. A=空 device_key", ok,
           f"HTTP {r.status_code}, msg={r.json().get('message')}")

    # ── Scenario 2: A=无效 device_key ────────────────────────────────────────
    log("\n══ Scenario 2: A=无效 device_key ══")
    t2 = f"s2-invalid-{int(time.time())}"
    r = send_cmd(token, {"device_key": "evo_this_key_does_not_exist", "command_type": "chat",
                          "thread_id": t2, "content": {"text": "hello"}})
    log(f"  HTTP {r.status_code}: {r.text[:80]}")
    ok = r.status_code == 403 and "device not found" in r.text
    record("2. A=无效 device_key (不存在)", ok,
           f"HTTP {r.status_code}, msg={r.json().get('message')}")

    # ── Scenario 3: A=他人设备 ────────────────────────────────────────────────
    log("\n══ Scenario 3: A=他人设备 (member_id=2 的设备) ══")
    # 先注入 Redis
    injected = redis_set(f"device:{FAKE_OTHER_DEVICE_KEY}", FAKE_OTHER_DEVICE_JSON)
    log(f"  Redis inject other-user device: {'OK' if injected else 'FAILED'}")
    t3 = f"s3-other-{int(time.time())}"
    r = send_cmd(token, {"device_key": FAKE_OTHER_DEVICE_KEY, "command_type": "chat",
                          "thread_id": t3, "content": {"text": "hello"}})
    log(f"  HTTP {r.status_code}: {r.text[:100]}")
    ok = r.status_code == 403 and "not belongs" in r.text
    record("3. A=他人设备 (403 not belongs to you)", ok,
           f"HTTP {r.status_code}, msg={r.json().get('message')}")

    # ── Scenario 4A: A=在线 + B=全局(0) + 普通问题 ───────────────────────────
    log("\n══ Scenario 4A: A=在线 + B=全局(0) + 普通问题 ══")
    t4a = f"s4a-global-qa-{int(time.time())}"
    r = send_cmd(token, {"device_key": online_device_key, "command_type": "chat",
                          "thread_id": t4a, "project_id": 0,
                          "content": {"text": "Reply with exactly: 'GLOBAL_MODE_GENERAL_OK'"}})
    log(f"  HTTP {r.status_code}")
    ai = wait_for_ai_response(t4a, timeout=35)
    log(f"  AI: {ai[:80]}")
    ok = len(ai.strip()) > 0
    record("4A. A=在线 + B=全局(0) + 普通问答", ok,
           f"AI: {ai[:60]}..." if ok else "No AI response within timeout")

    # ── Scenario 4B: A=在线 + B=全局(0) + 项目工具请求 ──────────────────────
    log("\n══ Scenario 4B: A=在线 + B=全局(0) + 项目工具 ══")
    t4b = f"s4b-global-tool-{int(time.time())}"
    r = send_cmd(token, {"device_key": online_device_key, "command_type": "chat",
                          "thread_id": t4b, "project_id": 0,
                          "content": {"text": "Use the edit_file tool to add a comment to README.md."}})
    log(f"  HTTP {r.status_code}")
    ai = wait_for_ai_response(t4b, timeout=40)
    log(f"  AI: {ai[:80]}")
    # Agent 在全局模式下无法使用项目工具，应提示没有 edit_file / 需要选择项目
    normalized_ai = ai.lower().replace("’", "'").replace("'", "")
    ok = any(kw.replace("'", "") in normalized_ai for kw in
             ["global","project","switch","select","specific","unable","cannot",
              "dont have","没有","项目","全局","not available","no.*tool"])
    record("4B. A=在线 + B=全局(0) + 项目工具 (应被拦截/提示)", ok,
           f"AI: {ai[:60]}..." if ok else f"Unexpected? AI: {ai[:60]}...")

    # ── Scenario 5: A=在线 + B=有效(121) ────────────────────────────────────
    log("\n══ Scenario 5: A=在线 + B=有效 project_id=121 ══")
    t5 = f"s5-proj121-{int(time.time())}"
    r = send_cmd(token, {"device_key": online_device_key, "command_type": "chat",
                          "thread_id": t5, "project_id": 121,
                          "content": {"text": "Reply with the exact phrase: 'Active project ID is 121'."}})
    log(f"  HTTP {r.status_code}")
    ai = wait_for_ai_response(t5, timeout=35)
    log(f"  AI: {ai[:80]}")
    ok = "121" in ai
    record("5. A=在线 + B=有效 project_id=121", ok,
           f"AI: {ai[:60]}..." if ok else f"Expected '121' in response, got: {ai[:60]}...")

    # ── Scenario 6: A=在线 + B=无效(99999) ──────────────────────────────────
    log("\n══ Scenario 6: A=在线 + B=无效 project_id=99999 ══")
    t6 = f"s6-invalid-proj-{int(time.time())}"
    r = send_cmd(token, {"device_key": online_device_key, "command_type": "chat",
                          "thread_id": t6, "project_id": 99999,
                          "content": {"text": "Tell me about the current project."}})
    log(f"  HTTP {r.status_code}")
    ai = wait_for_ai_response(t6, timeout=40)
    log(f"  AI: {ai[:80]}")
    # Gateway 应返回 200（不验证 project_id）；Agent 可能报错/降级/全局模式
    gw_ok = r.status_code == 200
    has_response = len(ai.strip()) > 0
    record("6. A=在线 + B=无效 project_id=99999 (Gateway透传)", gw_ok,
           f"HTTP {r.status_code} ({'✓' if gw_ok else '✗'}Gateway OK), "
           f"Agent response: {ai[:50] if has_response else '<no response / timeout>'}")

    # ── Scenarios 7A/B/C: A=离线设备 ─────────────────────────────────────────
    log("\n══ 注入离线设备到 Redis ══")
    injected_offline = redis_set(f"device:{FAKE_OFFLINE_DEVICE_KEY}", FAKE_OFFLINE_DEVICE_JSON)
    log(f"  Redis inject offline device: {'OK' if injected_offline else 'FAILED'}")

    for label, proj_id, proj_name in [
        ("7A", 0,     "全局(0)"),
        ("7B", 121,   "有效(121)"),
        ("7C", 99999, "无效(99999)"),
    ]:
        log(f"\n══ Scenario {label}: A=离线设备 + B={proj_name} ══")
        t = f"s{label.lower()}-offline-{int(time.time())}"
        payload = {"device_key": FAKE_OFFLINE_DEVICE_KEY, "command_type": "chat",
                   "thread_id": t, "project_id": proj_id,
                   "content": {"text": "hello from offline scenario"}}
        r = send_cmd(token, payload)
        log(f"  HTTP {r.status_code}: {r.text[:100]}")
        ok = r.status_code == 202 and "queued" in r.text
        record(f"{label}. A=离线 + B={proj_name} (202 queued)", ok,
               f"HTTP {r.status_code}, msg={r.json().get('message')}, "
               f"status={r.json().get('data', {}).get('status')}")
        time.sleep(1)

    return results


def main():
    log("=" * 60)
    log("EvoLoop 全维度路由测试（A×B×C 矩阵穷举）")
    log("=" * 60)

    token = login()
    online_device_key = get_online_device(token)

    try:
        results = run_tests(token, online_device_key)
    finally:
        # 清理测试注入的 Redis keys
        log("\n🧹 Cleaning up Redis test fixtures...")
        redis_del(f"device:{FAKE_OTHER_DEVICE_KEY}", f"device:{FAKE_OFFLINE_DEVICE_KEY}")
        log("  ✅ Redis cleanup done.")

    # ─── 汇总报告 ────────────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in results if ok)
    print("\n" + "=" * 65)
    print("EvoLoop 全维度路由测试结果报告")
    print("=" * 65)
    for name, ok, detail in results:
        print(f"[{'✅ PASSED' if ok else '❌ FAILED'}] {name}")
        print(f"   {detail}\n")
    print("-" * 65)
    print(f"Total: {len(results)} | Passed: {passed} | Failed: {len(results) - passed}")
    print("=" * 65)

    # ─── Markdown 报告 ────────────────────────────────────────────────────────
    md_lines = [
        "# EvoLoop 消息链路全维度路由测试报告（A×B×C 矩阵）\n",
        f"- **执行时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **在线设备**: `{online_device_key}`",
        f"- **结果**: {passed}/{len(results)} 通过\n",
        "## 测试矩阵覆盖\n",
        "| 维度 | 枚举值 |",
        "|------|--------|",
        "| A - device_key | 空 / 无效 / 他人设备 / 有效在线 / 有效离线 |",
        "| B - project_id | 全局(0) / 有效(121) / 无效(99999) |",
        "| C - 设备状态   | 在线 / 离线 |\n",
        "## 场景详细结果\n",
    ]
    for name, ok, detail in results:
        icon = "🟢" if ok else "🔴"
        md_lines.append(f"### {icon} {name}")
        md_lines.append(f"- **状态**: {'通过' if ok else '失败'}")
        md_lines.append(f"- **输出**: `{detail}`\n")

    report_path = "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/mobile/e2e-routing-matrix-report.md"
    with open(report_path, "w") as f:
        f.write("\n".join(md_lines))
    log(f"📄 Report written to {report_path}")


if __name__ == "__main__":
    main()
