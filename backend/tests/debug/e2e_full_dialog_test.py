#!/usr/bin/env python3
"""
完整对话链路端到端测试

验证：
  Mobile --HTTP /api/v1/message/send--> Gateway --WS command.relay--> Agent
    --> Agent 调 LLM --> Agent --HTTP /api/v1/message/send--> Gateway --WS--> Mobile
  --> 数据落库 MySQL

用法：
  uv run python tests/debug/e2e_full_dialog_test.py
"""

import asyncio
import json
import sys
import time
import uuid
import hmac
import hashlib
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
    """通过 PHP MC 登录接口获取 token。"""
    url = f"{mc_url.rstrip('/')}/api/login/login"
    resp = requests.post(url, json={"username": username, "password": password}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") not in (200, 0, "200", "0"):
        raise RuntimeError(f"MC 登录失败: {data}")
    token = data.get("data", {}).get("token") or data.get("token")
    if not token:
        raise RuntimeError(f"MC 登录响应中无 token: {data}")
    return token


def fetch_device_key(mc_url: str, token: str) -> str:
    """从 MC 获取用户的第一个设备 key。"""
    resp = requests.get(
        f"{mc_url.rstrip('/')}/evolooplink/api/device/list",
        headers={"token": token},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取设备列表失败: {data}")
    devices = data.get("data", [])
    if not devices:
        raise RuntimeError("MC 中没有已注册的设备")
    return devices[0]["device_key"]


def db_query(sql: str) -> list[dict]:
    """Execute MySQL query and return results as list of dicts."""
    import subprocess
    result = subprocess.run(
        f"mysql {MYSQL_CRED} -e \"{sql}\"",
        shell=True, capture_output=True, text=True, timeout=5
    )
    if result.returncode != 0:
        print(f"  [DB] Query failed: {result.stderr[:200]}")
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


async def main(token: str, device_key: str) -> int:
    passed = 0
    failed = 0

    print("=" * 70)
    print("完整对话链路端到端测试")
    print("=" * 70)
    # thread_id 由服务端生成，Mobile 不传
    thread_id = ""
    print(f"Gateway: {GATEWAY_HTTP}")
    print(f"Key:     {device_key}")
    print("-" * 70)

    # ── Step 0: Ensure Gateway is alive ──
    try:
        r = requests.get(f"{GATEWAY_HTTP}/health", timeout=3)
        assert r.status_code == 200
        log("Gateway ready")
    except Exception as e:
        print(f"Gateway not reachable: {e}")
        return 1

    # ── Step 1: Connect Agent WebSocket ──
    log("Connecting Agent WS...")
    try:
        agent_ws = await websockets.connect(f"{GATEWAY_WS}/ws?token={token}")
        await agent_ws.send(json.dumps({
            "version": "2.0", "type": "connect",
            "message_id": f"agent-{uuid.uuid4().hex[:8]}",
            "timestamp": int(time.time()),
            "body": {
                "device_type": "agent", "device_key": device_key,
                "device_name": "E2E Dialog Test Agent", "os_info": "test",
            },
        }))
        resp = await asyncio.wait_for(agent_ws.recv(), timeout=5)
        data = json.loads(resp)
        assert data.get("type") == "system.init", f"Expected system.init, got {data.get('type')}"
        log("Agent connected ✓")
        passed += 1
    except Exception as e:
        print(f"Agent WS connect failed: {e}")
        return 1

    # ── Step 2: Connect Mobile WebSocket ──
    log("Connecting Mobile WS...")
    try:
        mobile_ws = await websockets.connect(f"{GATEWAY_WS}/ws?token={token}")
        await mobile_ws.send(json.dumps({
            "version": "2.0", "type": "connect",
            "message_id": f"mobile-{uuid.uuid4().hex[:8]}",
            "timestamp": int(time.time()),
            "body": {"device_type": "mobile"},
        }))
        resp = await asyncio.wait_for(mobile_ws.recv(), timeout=5)
        data = json.loads(resp)
        assert data.get("type") == "system.init", f"Expected system.init, got {data.get('type')}"
        log("Mobile connected ✓")
        passed += 1
    except Exception as e:
        print(f"Mobile WS connect failed: {e}")
        return 1

    # Drain mobile buffer
    await asyncio.sleep(0.5)
    for _ in range(10):
        try:
            await asyncio.wait_for(mobile_ws.recv(), timeout=0.3)
        except asyncio.TimeoutError:
            break

    # ── Step 3: Mobile sends chat command (不传 thread_id/message_id，服务端生成) ──
    command_body = {
        "action": "chat",
        "content": {"text": "你是谁"},
    }
    envelope = {
        "version": "2.0", "type": "command.relay",
        "message_id": "", "timestamp": int(time.time()),
        "body": command_body,
    }
    payload = {"target_device_key": device_key, "envelope": envelope}

    log("Mobile sends HTTP POST /api/v1/message/send...")
    t0 = time.time()
    try:
        resp = requests.post(
            f"{GATEWAY_HTTP}/api/v1/message/send",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("code") == 0, f"Gateway error: {data}"
        log(f"Mobile HTTP send OK ({(time.time()-t0)*1000:.0f}ms) ✓")
        passed += 1
    except Exception as e:
        print(f"Mobile HTTP send failed: {e}")
        failed += 1
        await agent_ws.close()
        await mobile_ws.close()
        return 1

    # ── Step 4: Agent receives command.relay（获取服务端生成的 thread_id/message_id）──
    log("Agent waiting for command.relay...")
    try:
        agent_msg = await asyncio.wait_for(agent_ws.recv(), timeout=5)
        agent_data = json.loads(agent_msg)
        assert agent_data.get("type") == "command.relay", f"Expected command.relay, got {agent_data.get('type')}"
        cmd_body = agent_data.get("body", {})
        thread_id = cmd_body.get("thread_id", "")
        message_id = cmd_body.get("message_id", "")
        recv_cmd_id = cmd_body.get("command_id")
        assert thread_id, "Server did not generate thread_id"
        assert message_id, "Server did not generate message_id"
        assert cmd_body.get("action") == "chat", f"action mismatch"
        log(f"Agent received command.relay ✓ (thread={thread_id}, msg={message_id}, cmd={recv_cmd_id})")
        passed += 1
    except Exception as e:
        print(f"Agent did not receive command.relay: {e}")
        failed += 1
        await agent_ws.close()
        await mobile_ws.close()
        return 1

    # ── Step 5: Agent calls LLM (via Gateway) ──
    log("Agent calling LLM...")
    t1 = time.time()
    try:
        llm_resp = requests.post(
            f"{GATEWAY_HTTP}/v1/chat/completions",
            json={
                "model": "kimi-k2-thinking-turbo",
                "messages": [{"role": "user", "content": "Hello, what is 1+1?"}],
                "stream": False,
                "max_tokens": 200,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        assert llm_resp.status_code == 200, f"LLM HTTP {llm_resp.status_code}: {llm_resp.text[:200]}"
        llm_data = llm_resp.json()
        ai_content = llm_data["choices"][0]["message"]["content"]
        reasoning = llm_data["choices"][0]["message"].get("reasoning_content", "")
        usage = llm_data.get("usage", {})
        log(f"LLM replied: \"{ai_content[:80]}...\" ({(time.time()-t1)*1000:.0f}ms, tokens={usage.get('total_tokens','?')}) ✓")
        passed += 1
    except Exception as e:
        print(f"LLM call failed: {e}")
        # Use fallback content
        ai_content = "1 + 1 = 2. This is a test response."
        reasoning = ""
        log(f"LLM failed, using fallback response")
        failed += 1

    # ── Step 6: Agent sends AI reply back (via MobileChannel HTTP) ──
    reply_message_id = str(uuid.uuid4())
    sync_body = {
        "device_key": device_key,
        "sync_mode": "incremental",
        "thread_id": thread_id,
        "conversation": {
            "id": thread_id,
            "title": "E2E Dialog Test",
        },
        "messages": [{
            "message_id": reply_message_id,
            "thread_id": thread_id,
            "role": "ai",
            "content": ai_content,
            "content_type": "text",
            "created_at": int(time.time()),
            "sequence_number": 1,
            "device_key": device_key,
        }],
    }
    sync_envelope = {
        "version": "2.0", "type": "message.sync",
        "message_id": reply_message_id, "timestamp": int(time.time()),
        "body": sync_body,
    }
    reply_payload = {"target_device_key": "", "envelope": sync_envelope}

    log("Agent sends AI reply via HTTP POST /api/v1/message/send...")
    t2 = time.time()
    try:
        resp = requests.post(
            f"{GATEWAY_HTTP}/api/v1/message/send",
            json=reply_payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body.get("code") == 0, f"Gateway error: {body}"
        log(f"Agent HTTP send OK ({(time.time()-t2)*1000:.0f}ms) ✓")
        passed += 1
    except Exception as e:
        print(f"Agent HTTP send failed: {e}")
        failed += 1

    # ── Step 7: Mobile receives AI reply ──
    log("Mobile waiting for AI reply...")
    try:
        mobile_msg = await asyncio.wait_for(mobile_ws.recv(), timeout=10)
        mobile_data = json.loads(mobile_msg)
        assert mobile_data.get("type") == "message.sync", f"Expected message.sync, got {mobile_data.get('type')}"
        body = mobile_data.get("body", {})
        messages = body.get("messages", [])
        assert len(messages) > 0, "No messages in reply"
        assert messages[0].get("role") == "ai", f"Expected ai role, got {messages[0].get('role')}"
        reply_text = messages[0].get("content", "")
        log(f"Mobile received AI reply: \"{reply_text[:80]}...\" ✓ ({(time.time()-t0)*1000:.0f}ms total)")
        passed += 1
    except Exception as e:
        print(f"Mobile did not receive AI reply: {e}")
        failed += 1

    # ── Step 8: Verify data in MySQL ──
    log("Verifying MySQL persistence (waiting 5s for PHP worker)...")
    await asyncio.sleep(5)
    try:
        convs = db_query(f"SELECT id, title, created_at FROM evoloop_conversations WHERE id='{thread_id}'")
        if convs:
            log(f"Conversation found: id={convs[0]['id']}, title={convs[0]['title']}")
            passed += 1
        else:
            log("Conversation not found in DB yet (may need PHP worker to process)")
            failed += 1

        msgs = db_query(f"SELECT thread_id, role, LEFT(content,60) as preview FROM evoloop_messages WHERE thread_id='{thread_id}'")
        if msgs:
            log(f"Messages found in DB: {len(msgs)}")
            for m in msgs:
                log(f"  role={m['role']}: {m['preview'][:50]}")
            passed += 1
        else:
            log("Messages not found in DB yet")
            failed += 1
    except Exception as e:
        print(f"DB check failed: {e}")
        failed += 1

    # ── Cleanup ──
    await agent_ws.close()
    await mobile_ws.close()

    # ── Summary ──
    total = passed + failed
    print("\n" + "=" * 70)
    print(f"结果: {passed}/{total} 通过 ({failed} 失败)")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="完整对话链路端到端测试")
    parser.add_argument("--mc-url", default=MC_URL, help="PHP MC 地址")
    parser.add_argument("--gateway", default=GATEWAY_HTTP, help="Gateway HTTP 地址")
    parser.add_argument("--username", default="preterchan", help="MC 登录用户名")
    parser.add_argument("--password", default="hellomylife", help="MC 登录密码")
    parser.add_argument("--device-key", default=None, help="指定 device_key（默认从 MC 自动获取）")
    args = parser.parse_args()

    GATEWAY_HTTP = args.gateway
    GATEWAY_WS = args.gateway.replace("http://", "ws://").replace("https://", "wss://")
    MC_URL = args.mc_url

    print("[E2E] 登录 MC...")
    token = login_mc(MC_URL, args.username, args.password)

    device_key = args.device_key
    if not device_key:
        print("[E2E] 获取设备列表...")
        device_key = fetch_device_key(MC_URL, token)
    print(f"[E2E] 使用 member_id=1, device_key={device_key}")

    exit(asyncio.run(main(token, device_key)))
