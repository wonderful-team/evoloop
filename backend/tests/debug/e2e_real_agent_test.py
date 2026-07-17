#!/usr/bin/env python3
"""
真实 Agent 端到端对话链路测试

Mobile 发消息 → Gateway 路由 → 真实 Desktop Agent → LLM 回复 → 回传 Mobile → 落库 MySQL

用法：
  uv run python tests/debug/e2e_real_agent_test.py --username preterchan --password hellomylife
"""

import asyncio
import json
import sys
import time
import uuid
import argparse

import requests
import websockets

GATEWAY_HTTP = "http://127.0.0.1:9001"
GATEWAY_WS = "ws://127.0.0.1:9001"
MC_URL = "http://127.0.0.1:9002"
MYSQL_CRED = "-h127.0.0.1 -P3306 -uroot -padmin888 b2c_mall"


def log(msg: str):
    print(f"  [TEST] {msg}")


def login_mc(mc_url: str, username: str, password: str) -> str:
    url = f"{mc_url.rstrip('/')}/api/login/login"
    resp = requests.post(url, json={"username": username, "password": password}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") not in (200, 0, "200", "0"):
        raise RuntimeError(f"MC login failed: {data}")
    token = data.get("data", {}).get("token") or data.get("token")
    if not token:
        raise RuntimeError(f"No token in MC response: {data}")
    return token


def fetch_device_key(mc_url: str, token: str) -> str:
    resp = requests.get(
        f"{mc_url.rstrip('/')}/evolooplink/api/device/list",
        headers={"token": token},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Device list failed: {data}")
    devices = data.get("data", [])
    if not devices:
        raise RuntimeError("No devices found in MC")
    return devices[0]["device_key"]


def db_query(sql: str) -> list[dict]:
    import subprocess
    result = subprocess.run(
        f"mysql {MYSQL_CRED} -e \"{sql}\"",
        shell=True, capture_output=True, text=True, timeout=5
    )
    if result.returncode != 0:
        print(f"  [DB] Query error: {result.stderr[:200]}")
        return []
    lines = result.stdout.strip().split('\n')
    if len(lines) < 2:
        return []
    headers = [h.strip() for h in lines[0].split('\t')]
    rows = []
    for line in lines[1:]:
        vals = line.split('\t')
        rows.append(dict(zip(headers, vals)))
    return rows


async def main(token: str, device_key: str, gw_http: str, gw_ws: str, mc_url: str) -> int:
    passed = 0
    failed = 0

    print("=" * 70)
    print("真实 Agent 端到端对话链路测试")
    print("=" * 70)
    print(f"Gateway: {gw_http}")
    print(f"Device:  {device_key}")
    print("-" * 70)

    # ── Step 0: Health checks ──
    try:
        r = requests.get(f"{gw_http}/health", timeout=3)
        assert r.status_code == 200
        log("Gateway ready")
    except Exception as e:
        print(f"Gateway unreachable: {e}")
        return 1

    # ── Step 1: Verify real Agent is connected to Gateway ──
    try:
        r = requests.get(f"{gw_http}/api/v1/devices",
            headers={"Authorization": f"Bearer {token}"}, timeout=5)
        devices = r.json().get("data", {}).get("devices", [])
        online = [d for d in devices if d.get("status") == "online"]
        log(f"Online agents: {len(online)}")
        if not online:
            log("No online agent found — cannot test")
            return 1
        passed += 1
    except Exception as e:
        print(f"Device check failed: {e}")
        return 1

    # ── Step 2: Connect Mobile WebSocket ──
    log("Connecting Mobile WS...")
    try:
        mobile_ws = await websockets.connect(f"{gw_ws}/ws?token={token}")
        await mobile_ws.send(json.dumps({
            "version": "2.0", "type": "connect",
            "message_id": f"m-{uuid.uuid4().hex[:8]}",
            "timestamp": int(time.time()),
            "body": {"device_type": "mobile"},
        }))
        resp = await asyncio.wait_for(mobile_ws.recv(), timeout=5)
        data = json.loads(resp)
        assert data.get("type") == "system.init"
        log("Mobile connected ✓")
        passed += 1
    except Exception as e:
        print(f"Mobile WS failed: {e}")
        return 1

    # Drain initial messages
    await asyncio.sleep(0.5)
    for _ in range(10):
        try:
            await asyncio.wait_for(mobile_ws.recv(), timeout=0.3)
        except asyncio.TimeoutError:
            break

    # ── Step 3: Mobile sends chat message ──
    user_message = "请问，杭州今天天气怎么样？帮我写一段 Python 代码计算斐波那契数列的前20项"
    envelope = {
        "version": "2.0", "type": "command.relay",
        "message_id": "", "timestamp": int(time.time()),
        "body": {
            "action": "chat",
            "content": {"text": user_message},
        },
    }
    payload = {"target_device_key": device_key, "envelope": envelope}

    log(f"Mobile sends: \"{user_message[:40]}...\"")
    t0 = time.time()
    try:
        resp = requests.post(
            f"{gw_http}/api/v1/message/send",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("code") == 0
        log(f"HTTP send OK ({(time.time()-t0)*1000:.0f}ms) ✓")
        passed += 1
    except Exception as e:
        print(f"HTTP send failed: {e}")
        failed += 1
        await mobile_ws.close()
        return 1

    # ── Step 4: Wait for AI reply from real Agent ──
    log("Waiting for AI reply (LLM processing may take 5-30s)...")
    try:
        while True:
            mobile_msg = await asyncio.wait_for(mobile_ws.recv(), timeout=120)
            mobile_data = json.loads(mobile_msg)
            msg_type = mobile_data.get("type")
            log(f"Mobile received: type={msg_type}")
            if msg_type != "message.sync":
                # Drain control messages (command.ack, device.status, etc.)
                continue

            body = mobile_data.get("body", {})
            thread_id = body.get("thread_id", "")
            log(f"thread_id={thread_id}, created_at={body.get('created_at')}")

            # 真实 Agent 的 MobileChannel 发送的是 BlockMapper.to_mobile() 输出
            # body 中直接包含 role/content/id 等字段，非 messages 数组
            role = body.get("role", "")
            content = body.get("content", "")
            if role and content:
                log(f"AI reply ({role}): \"{content[:120]}...\"")
                log(f"Total round-trip: {(time.time()-t0)*1000:.0f}ms ✓")
            passed += 1

            # ── Step 5: Verify MySQL persistence ──
            log("Checking MySQL persistence (waiting 5s)...")
            await asyncio.sleep(5)
            try:
                convs = db_query(f"SELECT id, title FROM evoloop_conversations WHERE id='{thread_id}'")
                if convs:
                    log(f"Conversation: {convs[0]['title']} ✓")
                    passed += 1
                msgs = db_query(f"SELECT role, create_time FROM evoloop_messages WHERE thread_id='{thread_id}' ORDER BY sequence_number ASC")
                if msgs:
                    log(f"Messages in DB: {len(msgs)}")
                    for m in msgs:
                        log(f"  role={m['role']}: create_time={m['create_time']}")
                    passed += 1
                else:
                    log("No messages found in DB")
                    failed += 1
            except Exception as e:
                print(f"DB check failed: {e}")
                failed += 1
            break  # Exit after processing first message.sync
    except asyncio.TimeoutError:
        print("Timeout waiting for AI reply (>120s)")
        failed += 1
    except Exception as e:
        print(f"Reply error: {e}")
        failed += 1

    # ── Cleanup ──
    await mobile_ws.close()

    total = passed + failed
    print("\n" + "=" * 70)
    print(f"结果: {passed}/{total} 通过 ({failed} 失败)")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="真实 Agent 端到端测试")
    parser.add_argument("--mc-url", default=MC_URL)
    parser.add_argument("--gateway", default=GATEWAY_HTTP)
    parser.add_argument("--username", default="preterchan")
    parser.add_argument("--password", default="hellomylife")
    parser.add_argument("--device-key", default=None)
    args = parser.parse_args()

    # gw_http = args.gateway
    gw_ws = args.gateway.replace("http://", "ws://").replace("https://", "wss://")
    mc_url = args.mc_url

    print("[E2E] Logging into MC...")
    token = login_mc(mc_url, args.username, args.password)

    device_key = args.device_key
    if not device_key:
        print("[E2E] Fetching device list...")
        device_key = fetch_device_key(mc_url, token)
    print(f"[E2E] Using member_id=1, device_key={device_key}")

    exit(asyncio.run(main(token, device_key, GATEWAY_HTTP, GATEWAY_WS, MC_URL)))
