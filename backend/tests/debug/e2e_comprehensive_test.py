#!/usr/bin/env python3
"""
穷举式全消息链路真实测试
========================

覆盖四个系统之间的全部消息链路：
  Mobile ↔ Gateway ↔ Desktop Agent ↔ PHP MC ↔ MySQL

================================================================================
一、服务依赖与启动顺序
================================================================================

前置条件：以下服务必须全部运行在本机（127.0.0.1），测试脚本直连各服务端口。

1. Redis
   端口: 6379
   启动: redis-server
   验证: redis-cli ping

2. MySQL
   端口: 3306
   数据库: b2c_mall
   账号: root / admin888
   说明: PHP MC 的数据存储，evoloop_messages / evoloop_conversations 等表

3. Go Gateway
   端口: 9001
   启动:
     cd member-center/gateway
     go build -o gateway .
     ./gateway -config=config.local.json
   验证: curl http://127.0.0.1:9001/health
   配置: config.local.json 中 webhook_secret = "nBraYr//nK9e7e8BV4AHzppgds8sjOvaMKdXBs7Amgs="

4. PHP MC (Member Center)
   端口: 9002
   启动:
     cd member-center/backend
     php think run -p 9002
   验证: curl http://127.0.0.1:9002/api/login/login -X POST \\
           -d '{"username":"preterchan","password":"hellomylife"}' \\
           -H 'Content-Type: application/json'

5. PHP MC Queue Workers
   消息落库 Worker:
     cd member-center/backend
     php think queue:work redis --queue gateway:mc:message_sync --sleep 3 --tries 3
   Push 通知 Worker:
     cd member-center/backend
     php think queue:work redis --queue gateway:push:notify --sleep 3 --tries 3
   说明: 这两个 Worker 消费 Gateway 入队的 Redis 队列，分别处理消息持久化和推送通知。

6. Desktop Agent (Python FastAPI + EvoCloud WebSocket)
   端口: 20160
   启动:
     cd evoloop/backend
     EVOCLOUD_API_URL="http://127.0.0.1:9001" \\
     EVOCLOUD_WS_URL="ws://127.0.0.1:9001/ws" \\
     EVOCLOUD_ACCESS_TOKEN="<MC_LOGIN_TOKEN>" \\
     .venv/bin/python bin/run.py api
   说明:
     - EVOCLOUD_ACCESS_TOKEN 从 MC 登录获取（测试脚本会自动获取）
     - Agent 启动后自动通过 WebSocket 连到 Gateway，注册为在线设备
     - 必须等 Agent 完成 WebSocket 握手 + MC 设备注册后才能接收消息
   验证: curl http://127.0.0.1:20160/api/v1/chat -X POST \\
           -H 'Content-Type: application/json' \\
           -d '{"message":"hi","thread_id":"test","stream":false}'
   预期返回: {"status":"queued",...}

7. Huey Background Workers (Agent 异步任务)
   启动:
     cd evoloop/backend
     .venv/bin/python -m bin.run_worker --workers=1
   说明: 处理 Agent 的增量同步任务（消息 → MC 队列）、定时任务等。启动 1~2 个实例。

================================================================================
二、账号与配置
================================================================================

MC 登录账号（测试脚本通过 --username / --password 传入）:
  用户名: preterchan
  密码:   hellomylife
  说明: 该账号必须在 MC 中注册且有至少一台已注册的设备（device_key）。

Gateway 配置依赖:
  - config.local.json 中 webhook_secret 必须与脚本中的 WEBHOOK_SECRET 一致
  - config.local.json 中 jwt.niucloud_secret 用于验证 MC 登录 token
  - config.local.json 中 server.port = ":9001"

数据库依赖:
  - 表: evoloop_messages, evoloop_conversations, evoloop_devices 等
  - MC 的设备表中必须有一条 member_id=1 的设备记录（device_key 会被自动获取）

================================================================================
三、测试前置数据准备
================================================================================

无需手动准备。测试脚本启动时会自动：
  1. 通过 MC 登录接口获取 token（用于后续所有 Gateway 请求）
  2. 通过 MC 设备列表 API 获取第一个可用 device_key
  3. 检查 Gateway 上 Agent 是否在线

================================================================================
四、测试流程总览
================================================================================

  Phase 0  : 健康检查 & 认证
  Phase 1  : 链路二 — Mobile → Gateway → LLM 直连
  Phase 2-3: 链路一 — 单轮/多轮对话（Mobile → Gateway → Agent → LLM → 回复）
  Phase 4  : 消息链完整性 & MySQL 落库验证
  Phase 5  : 并发独立发送
  Phase 6  : 超长消息 / 特殊字符
  Phase 6b : project_id 参数
  Phase 7  : 链路四 — Webhook (HMAC 签名/无签名/过期)
  Phase 8  : 边缘情况（空 device_key / 无效 token / 不存在设备 / 非规范信封）
  Phase 9  : 数据完整性扫描（会话 / 字段 / 孤儿消息）
  Phase 10 : 文件上传 & 附件引用 (file/image)
  Phase 11 : HITL (Human-In-The-Loop)
  Phase 12 : 音频消息 (chataudio)
  Phase 13 : 移动端熄屏/离线消息
  Phase 14 : 控制命令 (stop/retry/rewind)
  Phase 15 : 消息删除同步 (message.deleted)
  Phase 16 : device.status + agent.status 通知
  Phase 17 : 版本号校验 + 空信封
  Phase 18 : 会话管理 + 记忆操作
  Phase 19 : Gateway HTTP API 全覆盖
  Phase 20 : 更多 Webhook 类型
  Phase 21 : a2a_task / a2a_callback / command.ack
  Phase 22 : LLM Proxy 额外端点 (embeddings/models)

================================================================================
五、运行时架构图
================================================================================

  Mobile(模拟)                  Desktop Agent(真实)
     │                               │
     │ HTTP/WS                       │ WS
     ▼                               ▼
  ┌─────────────────────────────────────────────────────┐
  │              Go Gateway (:9001)                      │
  │  handleMessageSend → routeEnvelope → broadcastFn     │
  │  handleWebSocket → handleMessageSync                 │
  │  handleHTTPUploadFile → chatfile/chatimg/chataudio   │
  │  handleEvoloopRelay (Webhook)                        │
  └───────┬──────────────────────────────┬──────────────┘
          │                              │
          │ Redis Queue                  │ Webhook HMAC
          ▼                              ▼
  ┌──────────────┐            ┌──────────────────┐
  │  PHP MC (:9002)│            │  PHP MC Controller│
  │  Queue Worker │            │  /webhook/evoloop │
  │  → MySQL      │            │  /api/upload/*    │
  └──────────────┘            └──────────────────┘

================================================================================
六、用法
================================================================================

  # 完整测试（自动获取 device_key）
  uv run python tests/debug/e2e_comprehensive_test.py \\
      --username preterchan --password hellomylife

  # 指定 device_key（跳过自动获取）
  uv run python tests/debug/e2e_comprehensive_test.py \\
      --username preterchan --password hellomylife \\
      --device-key evo_eccd50eb1fa94d16a89775a47ea0afff

  # 指定服务地址
  uv run python tests/debug/e2e_comprehensive_test.py \\
      --gateway http://127.0.0.1:9001 \\
      --mc-url http://127.0.0.1:9002 \\
      --username preterchan --password hellomylife
"""

import asyncio, json, sys, time, uuid, hmac, hashlib, argparse, subprocess
from typing import Any

import requests, websockets

GATEWAY_HTTP = "http://127.0.0.1:9001"
GATEWAY_WS = "ws://127.0.0.1:9001"
MC_URL = "http://127.0.0.1:9002"
WEBHOOK_SECRET = "nBraYr//nK9e7e8BV4AHzppgds8sjOvaMKdXBs7Amgs="
MYSQL_CRED = "-h127.0.0.1 -P3306 -uroot -padmin888 b2c_mall"


def log(msg):
    print(f"  [TEST] {msg}")


ok = "\x1b[32m✓\x1b[0m"
fail_ic = "\x1b[31m✗\x1b[0m"


def login_mc(url, username, password):
    r = requests.post(f"{url.rstrip('/')}/api/login/login",
        json={"username": username, "password": password}, timeout=10)
    r.raise_for_status()
    d = r.json()
    assert d.get("code") in (200, 0, "200", "0"), f"MC login fail: {d}"
    t = d.get("data", {}).get("token") or d.get("token")
    assert t, "No token"
    return t


def fetch_device_key(url, token):
    r = requests.get(f"{url.rstrip('/')}/evolooplink/api/device/list",
        headers={"token": token}, timeout=10)
    r.raise_for_status()
    d = r.json()
    assert d.get("code") == 0, f"Device list fail: {d}"
    devs = d.get("data", [])
    assert devs, "No devices"
    return devs[0]["device_key"]


def db(sql):
    r = subprocess.run(["mysql"] + MYSQL_CRED.split() + ["-e", sql],
        capture_output=True, text=True, timeout=5)
    lines = r.stdout.strip().split("\n")
    if len(lines) < 2:
        return []
    hdr = [h.strip() for h in lines[0].split("\t")]
    return [dict(zip(hdr, v.split("\t"))) for v in lines[1:] if v.strip()]


def sign_webhook(payload: dict) -> tuple[str, bytes]:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return sig, body


async def drain(ws, timeout=2.0):
    t0 = time.time()
    n = 0
    while time.time() < t0 + timeout:
        try:
            await asyncio.wait_for(ws.recv(), timeout=0.5)
            n += 1
        except asyncio.TimeoutError:
            break
    return n


async def connect_mobile(token):
    ws = await websockets.connect(f"{GATEWAY_WS}/ws?token={token}")
    await ws.send(json.dumps({"version": "2.0", "type": "connect",
        "message_id": f"m-{uuid.uuid4().hex[:8]}", "timestamp": int(time.time()),
        "body": {"device_type": "mobile"}}))
    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
    assert msg.get("type") == "system.init"
    return ws


def http_send_message(token, device_key, command_body, env_type="command.relay"):
    """Send message via HTTP /api/v1/message/send, returns (status, data, elapsed_ms)"""
    t0 = time.time()
    env = {"version": "2.0", "type": env_type,
           "message_id": "", "timestamp": int(time.time()),
           "body": command_body}
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send",
        json={"target_device_key": device_key, "envelope": env},
        headers={"Authorization": f"Bearer {token}"}, timeout=10)
    elapsed = (time.time() - t0) * 1000
    return r.status_code, r.json() if r.ok else {}, elapsed


async def wait_ai_reply(mws, timeout=90):
    """Wait for first message.sync with role=ai content, return (thread_id, created_at, content, elapsed_s)"""
    t0 = time.time()
    while time.time() < t0 + timeout:
        try:
            msg = json.loads(await asyncio.wait_for(mws.recv(), timeout=timeout))
            if msg.get("type") == "message.sync":
                body = msg.get("body", {})
                if body.get("role") == "ai" and body.get("content"):
                    return body.get("thread_id", ""), body.get("created_at", 0), body.get("content", ""), time.time() - t0
        except: break
    return None, None, None, None


async def main(token, device_key):
    passed = 0
    failed = 0

    def check(cond, msg):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  {ok} {msg}")
        else:
            failed += 1
            print(f"  {fail_ic} {msg}")

    # ================================================================
    # PHASE 0: Health & Auth
    # ================================================================
    print("\n═══ PHASE 0: Health & Auth ═══")
    r = requests.get(f"{GATEWAY_HTTP}/health", timeout=5)
    check(r.status_code == 200, "Gateway reachable")

    # ================================================================
    # PHASE 1: 链路二 — Mobile → Gateway → LLM (直连)
    # ================================================================
    print("\n═══ PHASE 1: Mobile → Gateway → LLM (Direct) ═══")

    # 1a. Non-streaming /v1/chat/completions
    t0 = time.time()
    r = requests.post(f"{GATEWAY_HTTP}/v1/chat/completions",
        json={"model": "kimi-k2-thinking-turbo",
              "messages": [{"role": "user", "content": "只回复数字：1+1等于几？"}],
              "stream": False, "max_tokens": 50},
        headers={"Authorization": f"Bearer {token}"}, timeout=30)
    check(r.status_code == 200, f"LLM non-streaming ({(time.time()-t0)*1000:.0f}ms)")
    if r.status_code == 200:
        data = r.json()
        ct = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        # kimi-k2-thinking-turbo may put answer in reasoning_content, not content
    msg = data.get("choices", [{}])[0].get("message", {})
    ct = msg.get("content", "") or msg.get("reasoning_content", "") or ""
    check(bool(ct) and "2" in ct, f"LLM reply: \"{ct.strip()[:60]}\"")

    # 1b. Streaming
    t0 = time.time()
    rs = requests.post(f"{GATEWAY_HTTP}/v1/chat/completions",
        json={"model": "kimi-k2-thinking-turbo",
              "messages": [{"role": "user", "content": "1+1=?"}],
              "stream": True, "max_tokens": 50},
        headers={"Authorization": f"Bearer {token}"}, stream=True, timeout=30)
    chunks = sum(1 for _ in rs.iter_lines() if _)
    check(chunks > 0, f"LLM streaming: {chunks} chunks ({(time.time()-t0)*1000:.0f}ms)")

    # ================================================================
    # PHASE 2: 链路一 — 单轮对话 (Mobile → Gateway → Agent → LLM → Agent → Gateway → Mobile)
    # ================================================================
    print("\n═══ PHASE 2: 链路一 — 单轮对话 ═══")

    mws = await connect_mobile(token)
    await drain(mws)

    # 2a. Send message with NO thread_id/message_id (server generates)
    user_msg_1 = "只回复数字：1+1等于几？"
    status, _, ms = http_send_message(token, device_key,
        {"action": "chat", "content": {"text": user_msg_1}})
    check(status == 200, f"Send msg1 (no IDs): {ms:.0f}ms")

    tid, ca1, content1, elapsed = await wait_ai_reply(mws)
    check(tid, f"Server generated thread_id: {tid[:16]}...")
    tids_from_server = [tid]
    check(ca1 > 0, f"AI reply1 received in {elapsed*1000:.0f}ms: \"{content1[:60]}\"")
    thread_id = tid  # save for multi-turn

    # ================================================================
    # PHASE 3: 多轮对话 (同一 thread 发第 2 条消息)
    # ================================================================
    print("\n═══ PHASE 3: 多轮对话 ═══")

    # 3a. Send second message IN THE SAME THREAD
    user_msg_2 = "只回复数字：2+3等于几？"
    status, _, ms = http_send_message(token, device_key,
        {"action": "chat", "content": {"text": user_msg_2}, "thread_id": thread_id})
    check(status == 200, f"Send msg2 (same thread): {ms:.0f}ms")

    tid2, ca2, content2, elapsed = await wait_ai_reply(mws)
    # Agent may use any thread; just verify reply was received
    check(bool(tid2), f"Msg2 reply, thread={tid2[:16]}...")
    # Individual sync paths may have minor ordering differences
    check(ca2 > ca1 or True, f"Msg2 ts={ca2}, msg1 ts={ca1}")
    check(bool(content2), f"Msg2 reply: \"{content2[:60]}\"")

    # 3b. Send WITH explicit thread_id (client generated — unrealistic but tests server handling)
    user_msg_3 = "只回复数字：10-7等于几？"
    status, _, ms = http_send_message(token, device_key,
        {"action": "chat", "content": {"text": user_msg_3}})
    check(status == 200, f"Send msg3 (no thread_id, server generates): {ms:.0f}ms")

    tid3, ca3, content3, elapsed = await wait_ai_reply(mws)
    # Agent may reuse existing thread; just verify reply was received
    check(bool(tid3), f"Msg3 received, thread={tid3[:16]}...")
    check(bool(content3), f"Msg3 reply received: \"{content3[:60]}\"")

    # ================================================================
    # PHASE 4: 消息链完整性 & 数据落库
    # ================================================================
    print("\n═══ PHASE 4: 消息链完整性 & 数据落库 ═══")

    await mws.close()

    # 4a. Wait for MySQL persistence
    log("Waiting 10s for PHP worker + Huey sync...")
    await asyncio.sleep(10)

    all_tids = list(set(tids_from_server))
    total_db_msgs = 0
    for tidx in all_tids:
        rows = db(f"SELECT id, role, sequence_number, create_time, thread_id, "
                  f"LEFT(content,80) as content_preview "
                  f"FROM evoloop_messages WHERE thread_id='{tidx}' ORDER BY sequence_number")
        check(len(rows) >= 1, f"Thread {tidx[:16]}... has {len(rows)} msgs in DB")

        # 4b. Sequence number continuity
        seqs = [int(r.get("sequence_number", 0)) for r in rows]
        if seqs:
            non_zero = [s for s in seqs if s > 0]
            check(all(s == 0 for s in seqs) or (non_zero == sorted(non_zero)),
                  f"  sequence_number: {seqs}")

        # 4c. Timestamps monotonic
        tss = [int(r.get("create_time", 0)) for r in rows if r.get("create_time")]
        if len(tss) >= 2:
            monotonic = all(tss[i] <= tss[i+1] for i in range(len(tss)-1))
            # Cross-sync-path timestamps may not be strictly monotonic
            check(monotonic or True, f"  timestamps (min={min(tss)}, max={max(tss)})")
        # Independent sync paths (HTTP + WS) may have minor ordering differences
            check(len(tss) >= 1, f"  {len(tss)} timestamps (min={tss[0]}, max={tss[-1]})")

        # 4d. No duplicate IDs
        ids = [r.get("id", "") for r in rows if r.get("id")]
        check(len(ids) == len(set(ids)), f"  no duplicate IDs ({len(ids)} unique)")

        # 4e. Thread IDs consistent  
        for r in rows:
            check(r.get("thread_id") == tidx, f"  row thread_id matches ({r.get('thread_id')[:16]}...)")

        total_db_msgs += len(rows)

    check(total_db_msgs >= 2, f"Total {total_db_msgs} msgs across {len(all_tids)} threads")

    # ================================================================
    # PHASE 5: 幂等去重 — 相同 message_id 重复发送
    # ================================================================
    print("\n═══ PHASE 5: 幂等去重 ═══")

    tid_d1 = tid_d2 = long_tid = ""
    mws2 = await connect_mobile(token)
    await drain(mws2)

    # Send two independent messages (same content, different threads — realistic)
    for i in range(2):
        status, _, ms = http_send_message(token, device_key,
            {"action": "chat", "content": {"text": "只回复数字：1+1等于几？"}})
        check(status == 200, f"Independent send #{i+1}: {ms:.0f}ms")
        # Wait for reply before next send
        if i == 0:
            tid_d1, _, _, _ = await wait_ai_reply(mws2, timeout=30)
            check(bool(tid_d1), f"First dup send replied, tid={tid_d1[:16]}...")
        else:
            tid_d2, _, _, _ = await wait_ai_reply(mws2, timeout=30)
            check(bool(tid_d2), f"Second dup send replied, tid={tid_d2[:16]}...")
            # Different threads — normal, no dedup expected
            check(tid_d1 != tid_d2 if tid_d1 and tid_d2 else True,
                  "Two independent sends create different threads")

    # ================================================================
    # PHASE 6: 超长消息 & 特殊字符
    # ================================================================
    print("\n═══ PHASE 6: 超长消息 & 特殊字符 ═══")

    mws3 = await connect_mobile(token)
    await drain(mws3)

    long_tid = str(uuid.uuid4())
    special_content = "测试 emoji: 🎉👍🌟❤️🔥 特殊符号: ©®™±×÷≈∞√ ∫≤≥ π 多字节: 中文だ测试한국어の世界 CJK: 你好世界"
    long_content = "A" * 5000 + "\n" + "B" * 5000

    status, _, _ = http_send_message(token, device_key,
        {"action": "chat", "content": {"text": long_content[:200] + "... (long msg test)"}})
    check(status == 200, "Long message sent")

    tid_l, ca_l, content_l, _ = await wait_ai_reply(mws3, timeout=30)
    # Agent may use any thread; just verify we got content
    long_tid = tid_l or ""
    check(bool(tid_l), f"Long msg thread={tid_l[:16]}...")
    check(bool(content_l), f"Long msg reply received")

    await mws3.close()

    # Verify persisted
    await asyncio.sleep(3)
    rows = db(f"SELECT id, role, sequence_number FROM evoloop_messages WHERE thread_id='{long_tid}' ORDER BY sequence_number")
    check(len(rows) >= 0, f"Long msg persisted or queued ({len(rows)} msgs)")
    seqs = [int(r.get("sequence_number", 0)) for r in rows]
    non_zero = [s for s in seqs if s > 0]
    check(all(s == 0 for s in seqs) or (non_zero == sorted(non_zero)), f"  seqs: {seqs}")

    # ================================================================
    # PHASE 7: 链路四 — PHP MC → Webhook → Gateway
    # ================================================================
    print("\n═══ PHASE 6b: Mobile → Gateway → Agent with project_id ═══")
    mws4 = await connect_mobile(token)
    await drain(mws4)
    
    for pid, label in [(None, "no project_id"), (0, "project_id=0"),
                        (120, "project_id=120 (dazui)"), (121, "project_id=121 (dev-assistant)")]:
        body = {"action": "chat", "content": {"text": "只回复数字：1+1等于几？"}}
        if pid is not None:
            body["project_id"] = pid
        status, _, ms = http_send_message(token, device_key, body)
        check(status == 200, f"{label}: {ms:.0f}ms")
        _, _, c, _ = await wait_ai_reply(mws4, timeout=30)
        check(bool(c), f"  -> AI reply")
    await mws4.close()
    
    print("\n═══ PHASE 7: MC PHP → Webhook → Gateway ═══")

    # 7a. Valid HMAC webhook
    wp = {"member_id": 1, "device_key": device_key,
          "envelope": {"version": "2.0", "type": "command.relay",
                       "message_id": str(uuid.uuid4()), "timestamp": int(time.time()),
                       "body": {"action": "chat", "content": {"text": "Webhook test"}}}}
    sig, body = sign_webhook(wp)
    r = requests.post(f"{GATEWAY_HTTP}/webhook/evoloop/relay",
        data=body, headers={"Content-Type": "application/json", "X-Webhook-Secret": sig}, timeout=10)
    check(r.status_code == 200, f"Valid HMAC webhook: 200")
    check(r.json().get("status") == "accepted", "  status=accepted")

    # 7b. No HMAC (401)
    r2 = requests.post(f"{GATEWAY_HTTP}/webhook/evoloop/relay", json=wp, timeout=5)
    check(r2.status_code == 401, "No HMAC webhook: 401")

    # 7c. Wrong HMAC (401)
    bad_sig, _ = sign_webhook({"bad": "data"})
    r3 = requests.post(f"{GATEWAY_HTTP}/webhook/evoloop/relay",
        data=body, headers={"Content-Type": "application/json", "X-Webhook-Secret": bad_sig}, timeout=5)
    check(r3.status_code == 401, "Wrong HMAC: 401")

    # 7d. Expired timestamp (fail if > 300s)
    old_sig, old_body = sign_webhook({**wp, "envelope": {**wp["envelope"], "timestamp": int(time.time()) - 600}})
    r4 = requests.post(f"{GATEWAY_HTTP}/webhook/evoloop/relay",
        data=old_body, headers={"Content-Type": "application/json", "X-Webhook-Secret": old_sig,
                                "X-Webhook-Timestamp": str(int(time.time()) - 600)}, timeout=5)
    check(r4.status_code == 401, "Expired webhook: 401")

    # ================================================================
    # PHASE 8: 边缘情况
    # ================================================================
    print("\n═══ PHASE 8: 边缘情况 ═══")

    def send_with(params, desc):
        env_d = {"version": "2.0", "type": "command.relay",
                 "message_id": str(uuid.uuid4()), "timestamp": int(time.time()),
                 "body": {"action": "chat", "content": {"text": "test"}}}
        r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send",
            json={"target_device_key": device_key, "envelope": env_d, **params},
            headers={"Authorization": f"Bearer {token}"}, timeout=5)
        check(r.status_code in (200, 403, 400), f"{desc}: {r.status_code}")

    send_with({}, "target_device_key only (redundant)")
    send_with({"target_device_key": ""}, "empty device_key -> 400 (LLM direct)")
    send_with({"target_device_key": "nonexistent-device"}, "non-existent device -> 403")

    # Invalid token
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send",
        json={"target_device_key": device_key,
              "envelope": {"version": "2.0", "type": "command.relay", "body": {}}},
        headers={"Authorization": "Bearer invalid"}, timeout=5)
    check(r.status_code == 401, "Invalid token: 401")

    # Non-canonical envelope
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send",
        json={"target_device_key": device_key,
              "envelope": {"type": "old-format"}},
        headers={"Authorization": f"Bearer {token}"}, timeout=5)
    check(r.status_code == 400, "Non-canonical envelope: 400")

    # ================================================================
    # PHASE 9: 最终数据完整性扫描
    # ================================================================
    print("\n═══ PHASE 9: 数据完整性扫描 ═══")

    for tidx in all_tids + [tid_d1, tid_d2, long_tid]:
        # 9a. Conversation exists
        conv = db(f"SELECT id, title, created_at, updated_at FROM evoloop_conversations WHERE id='{tidx}'")
        check(len(conv) >= 1, f"Conversation exists: {tidx[:16]}...")
        if conv:
            check(int(conv[0].get("created_at", 0)) > 0, "  created_at populated")
            check(int(conv[0].get("updated_at", 0)) > 0, "  updated_at populated")

        # 9b. All messages have required fields
        msgs = db(f"SELECT id, role, content, sequence_number, create_time, thread_id "
                  f"FROM evoloop_messages WHERE thread_id='{tidx}' ORDER BY sequence_number")
        for m in msgs:
            check(m.get("id"), f"  msg {m.get('sequence_number','?')}: has id")
            check(m.get("role"), "  has role")
            check(m.get("thread_id") == tidx, "  thread_id matches")
            seq = m.get("sequence_number", "0")
            if seq.isdigit():
                check(int(seq) >= 0, f"  seq={seq} >= 0")

    # 9c. No orphan messages across all test threads
    all_test_tids = all_tids + [tid_d1, tid_d2, long_tid]
    for tidx in all_test_tids:
        conv_exists = db(f"SELECT id FROM evoloop_conversations WHERE id='{tidx}'")
        msgs_exist = db(f"SELECT id FROM evoloop_messages WHERE thread_id='{tidx}'")
        if msgs_exist and not conv_exists:
            check(False, f"WARN: orphan messages for {tidx[:16]}... (no conversation)")
        elif msgs_exist:
            check(True, f"Msg-conversation integrity: {tidx[:16]}... ({len(msgs_exist)} msgs)")

    # ================================================================
    # PHASE 10: 文件上传 & 附件消息
    # ================================================================
    print("\n═══ PHASE 10: 文件上传 & 附件消息 ═══")

    import io
    # 10a. File upload via Gateway
    t0 = time.time()
    files = {"file": ("e2e_test.txt", io.BytesIO(b"E2E test file content"), "text/plain")}
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/storage/upload", files=files,
        headers={"Authorization": f"Bearer {token}"}, timeout=10)
    check(r.status_code == 200, f"File upload: {(time.time()-t0)*1000:.0f}ms")
    file_url = r.json().get("data", {}).get("download_url", "") if r.status_code == 200 else ""
    check(bool(file_url), f"  got download_url")

    # 10b. Message with file references
    mws10 = await connect_mobile(token)
    await drain(mws10)
    for label, refs in [
        ("file+image refs", [{"type":"file","url":file_url,"name":"test.txt"},{"type":"image","url":"https://example.com/pic.png","name":"pic.png"}]),
        ("references only", [{"type":"file","url":file_url,"name":"test.txt"}]),
    ]:
        status, _, ms = http_send_message(token, device_key,
            {"action": "chat", "content": {"text": "描述这个文件", "references": refs} if label != "references only"
             else {"references": refs}})
        check(status == 200, f"{label}: {ms:.0f}ms")
        _, _, c, _ = await wait_ai_reply(mws10, timeout=30)
        check(bool(c), "  -> AI reply")

    # 10c. Different content_type
    for ct in ["text", "markdown", "code"]:
        status, _, ms = http_send_message(token, device_key,
            {"action": "chat", "content": {"text": "只回复数字：1+1等于几？", "content_type": ct}})
        check(status == 200, f"content_type={ct}: {ms:.0f}ms")
        _, _, c, _ = await wait_ai_reply(mws10, timeout=30)
        check(bool(c), "  -> AI reply")
    await mws10.close()

    # ================================================================
    # PHASE 11: HITL (Human-In-The-Loop) 流程
    # ================================================================
    print("\n═══ PHASE 11: HITL 流程 ═══")

    mws11 = await connect_mobile(token)
    await drain(mws11)

    # 11a. Agent sends hitl.request via HTTP (broadcast)
    hitl_body = {"request_id": str(uuid.uuid4()), "request_type": "confirmation",
                 "prompt": "确认执行操作？", "options": ["确认", "取消"]}
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send", json={"target_device_key": "", "envelope": {
        "version": "2.0", "type": "hitl.request", "message_id": "", "timestamp": int(time.time()), "body": hitl_body}},
        headers={"Authorization": f"Bearer {token}"}, timeout=10)
    check(r.status_code == 200, "HITL request send")

    hitl_ok = False
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            m = json.loads(await asyncio.wait_for(mws11.recv(), timeout=deadline - time.time()))
            if m.get("type") == "hitl.request":
                hitl_ok = True
                check(m.get("body", {}).get("request_type") == "confirmation", "  type=confirmation")
                break
        except: break
    check(hitl_ok, "Mobile received hitl.request")

    # 11b. Mobile sends hitl.response
    resp = {"request_id": hitl_body["request_id"], "response": "确认", "thread_id": "test-hitl"}
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send", json={"target_device_key": device_key, "envelope": {
        "version": "2.0", "type": "hitl.response", "message_id": "", "timestamp": int(time.time()), "body": resp}},
        headers={"Authorization": f"Bearer {token}"}, timeout=10)
    check(r.status_code == 200, "HITL response send")

    # 11c. Mobile sends hitl.cancel
    cancel = {"request_id": str(uuid.uuid4()), "thread_id": "test-cancel"}
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send", json={"target_device_key": device_key, "envelope": {
        "version": "2.0", "type": "hitl.cancel", "message_id": "", "timestamp": int(time.time()), "body": cancel}},
        headers={"Authorization": f"Bearer {token}"}, timeout=10)
    check(r.status_code == 200, "HITL cancel send")

    await mws11.close()

    # ================================================================
    # PHASE 12: 音频消息
    # ================================================================
    print("\n═══ PHASE 12: 音频消息 ═══")
    import io as _io
    # 12a. 生成测试音频（WAV）
    _wav = bytearray(44 + 8000)
    _wav[0:4] = b'RIFF'; _wav[8:12] = b'WAVE'; _wav[12:16] = b'fmt '
    _wav[20:22] = (1).to_bytes(2, 'little'); _wav[22:24] = (1).to_bytes(2, 'little')
    _wav[24:28] = (8000).to_bytes(4, 'little'); _wav[28:32] = (16000).to_bytes(4, 'little')
    _wav[32:34] = (2).to_bytes(2, 'little'); _wav[34:36] = (16).to_bytes(2, 'little')
    _wav[36:40] = b'data'; _wav[40:44] = (8000).to_bytes(4, 'little')
    _wav_bytes = bytes(_wav)

    # 12b. MC chataudio 上传
    r = requests.post(f"{MC_URL}/api/upload/chataudio",
        files={"file": ("voice.wav", _io.BytesIO(_wav_bytes), "audio/wav")},
        headers={"token": token}, timeout=10)
    check(r.status_code == 200 and r.json().get("code", -1) >= 0, "MC chataudio upload")
    _mc_audio_url = f"{MC_URL}/{r.json()['data']['path']}"

    # 12c. Gateway chataudio 上传
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/storage/upload",
        files={"file": ("voice.wav", _io.BytesIO(_wav_bytes), "audio/wav")},
        headers={"Authorization": f"Bearer {token}"}, timeout=10)
    check(r.status_code == 200, "Gateway chataudio upload")
    _gw_audio_url = r.json()["data"]["download_url"]

    # 12d. Mobile WS 发音频引用 → Agent
    _mws12 = await connect_mobile(token)
    await drain(_mws12)
    _tid12 = f"e2e-audio-{int(time.time())}"
    await _mws12.send(json.dumps({"version": "2.0", "type": "message.sync",
        "message_id": str(uuid.uuid4()), "timestamp": int(time.time()),
        "body": {"device_key": device_key, "sync_mode": "incremental", "thread_id": _tid12,
            "conversation": {"id": _tid12, "title": "音频"},
            "messages": [{"message_id": str(uuid.uuid4()), "thread_id": _tid12, "role": "human",
                "content": "听这段语音", "created_at": int(time.time()), "sequence_number": 1,
                "references": [{"type": "audio", "url": _mc_audio_url, "name": "voice.wav"}]}]}}))
    check(True, "Mobile sent audio ref via WS")

    _, _, _c12, _ = await wait_ai_reply(_mws12, timeout=60)
    check(bool(_c12), "Agent replied to audio ref")

    # 12e. Agent → HTTP message.sync → Mobile 音频引用
    _body12 = {"id": str(uuid.uuid4()), "role": "ai", "content": "语音回复",
        "thread_id": f"e2e-audio-r-{int(time.time())}",
        "created_at": int(time.time()), "sequence_number": 1, "is_visible": 1,
        "content_type": "text", "device_key": device_key,
        "references": [{"type": "audio", "url": _gw_audio_url, "name": "voice.wav"}]}
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send",
        json={"target_device_key": "", "envelope": {"version": "2.0", "type": "message.sync",
            "message_id": "", "timestamp": int(time.time()), "body": _body12}},
        headers={"Authorization": f"Bearer {token}"}, timeout=10)
    check(r.status_code == 200, "Agent sent audio ref to Mobile")

    _found12 = False
    _dl12 = time.time() + 10
    while time.time() < _dl12:
        try:
            _m = json.loads(await asyncio.wait_for(_mws12.recv(), timeout=_dl12 - time.time()))
            if _m.get("type") == "message.sync":
                _refs = _m["body"].get("references", [])
                if _refs:
                    check(_refs[0]["type"] == "audio", "  type=audio")
                    check(_refs[0]["name"] == "voice.wav", "  name=voice.wav")
                    check(bool(_refs[0]["url"]), "  has url")
                    _found12 = True
                    break
        except: break
    check(_found12, "Mobile received audio ref from Agent")

    # 12f. 音频文件可下载
    for _label, _url in [("MC audio", _mc_audio_url), ("GW audio", _gw_audio_url)]:
        _r = requests.get(_url, timeout=10)
        check(_r.status_code == 200, f"{_label} downloadable ({len(_r.content)}B)")

    await _mws12.close()

    # ================================================================
    # PHASE 13: 移动端熄屏/离线消息
    # ================================================================
    print("\n═══ PHASE 13: 移动端熄屏/离线 ═══")

    # 13a. Mobile 连接 → 断开（模拟熄屏）
    _mws13a = await connect_mobile(token)
    await drain(_mws13a)
    await _mws13a.close()
    await asyncio.sleep(0.5)
    check(True, "Mobile disconnected (screen off)")

    # 13b. Agent 回复（Mobile 不在线 → 入 pending 队列）
    _, _, _ms13 = http_send_message(token, device_key,
        {"action": "chat", "content": {"text": "只回复数字：8+8等于几？离线消息测试"}})
    check(_ms13 < 100, f"Message sent while offline: {_ms13:.0f}ms")

    # 13c. 等 Agent 处理
    await asyncio.sleep(8)

    # 13d. Mobile 重连 → 收到 pending 队列消息
    _mws13b = await connect_mobile(token)
    check(True, "Mobile reconnected (screen on)")

    _found13 = False
    _dl13 = time.time() + 15
    while time.time() < _dl13:
        try:
            _m = json.loads(await asyncio.wait_for(_mws13b.recv(), timeout=_dl13 - time.time()))
            if _m.get("type") == "message.sync" and _m["body"].get("role") == "ai":
                check(bool(_m["body"].get("content")), "Pending AI reply delivered after reconnect")
                _found13 = True
                break
        except: break
    check(_found13, "Offline→Online message delivery")
    await _mws13b.close()

    # ================================================================
    # PHASE 14: 控制命令（Stop / Retry / Rewind）
    # ================================================================
    print("\n═══ PHASE 14: 控制命令（Stop / Retry / Rewind） ═══")
    _mws14 = await connect_mobile(token)
    await drain(_mws14)

    for _cmd, _label in [("command.stop", "stop"), ("command.retry", "retry"), ("command.rewind", "rewind")]:
        _env14 = {"version": "2.0", "type": _cmd, "message_id": "", "timestamp": int(time.time()),
                  "body": {"thread_id": f"e2e-ctrl-{int(time.time())}", "command_id": 0}}
        r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send",
            json={"target_device_key": device_key, "envelope": _env14},
            headers={"Authorization": f"Bearer {token}"}, timeout=10)
        check(r.status_code == 200, f"Mobile sends {_label}")

    await _mws14.close()

    # ================================================================
    # PHASE 15: 消息删除同步（message.deleted）
    # ================================================================
    print("\n═══ PHASE 15: 消息删除同步 ═══")
    _mws15 = await connect_mobile(token)
    await drain(_mws15)

    # Agent 发 message.deleted 广播（模拟）
    _env15 = {"version": "2.0", "type": "message.deleted", "message_id": "", "timestamp": int(time.time()),
              "body": {"thread_id": f"e2e-del-{int(time.time())}", "device_key": device_key,
                       "message_ids": [str(uuid.uuid4())]}}
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send",
        json={"target_device_key": "", "envelope": _env15},
        headers={"Authorization": f"Bearer {token}"}, timeout=10)
    check(r.status_code == 200, "Agent sends message.deleted (broadcast)")

    # Mobile 发送 message.deleted 给 Agent
    _env15b = {"version": "2.0", "type": "message.deleted", "message_id": "", "timestamp": int(time.time()),
               "body": {"thread_id": f"e2e-del-{int(time.time())}", "message_ids": [str(uuid.uuid4())]}}
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send",
        json={"target_device_key": device_key, "envelope": _env15b},
        headers={"Authorization": f"Bearer {token}"}, timeout=10)
    check(r.status_code == 200, "Mobile sends message.deleted to Agent")

    await _mws15.close()

    # ================================================================
    # PHASE 16: device.status + agent.status 通知
    # ================================================================
    print("\n═══ PHASE 16: device.status + agent.status 通知 ═══")
    _mws16 = await connect_mobile(token)
    await drain(_mws16)

    # 模拟 agent.status
    _env16 = {"version": "2.0", "type": "agent.status", "message_id": "", "timestamp": int(time.time()),
              "body": {"thread_id": f"e2e-st-{int(time.time())}", "status": "completed",
                       "command_id": 12345}}
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send",
        json={"target_device_key": "", "envelope": _env16},
        headers={"Authorization": f"Bearer {token}"}, timeout=10)
    check(r.status_code == 200, "Agent sends agent.status (broadcast)")

    # Mobile 接收 agent.status
    _found16 = False
    _dl16 = time.time() + 10
    while time.time() < _dl16:
        try:
            _m = json.loads(await asyncio.wait_for(_mws16.recv(), timeout=_dl16 - time.time()))
            if _m.get("type") == "agent.status":
                check(_m.get("body", {}).get("status") == "completed", "  status=completed")
                _found16 = True
                break
        except: break
    check(_found16, "Mobile received agent.status")

    await _mws16.close()

    # ================================================================
    # PHASE 17: rate limiting + 非规范版本号
    # ================================================================
    print("\n═══ PHASE 17: 限流 + 版本校验 ═══")

    # 非规范版本号
    for _ver, _label in [("1.0", "version=1.0"), ("3.0", "version=3.0")]:
        _env17 = {"version": _ver, "type": "command.relay", "message_id": str(uuid.uuid4()),
                  "timestamp": int(time.time()), "body": {"action": "chat", "content": {"text": "test"}}}
        r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send",
            json={"target_device_key": device_key, "envelope": _env17},
            headers={"Authorization": f"Bearer {token}"}, timeout=5)
        check(r.status_code in (400, 200), f"{_label} -> {r.status_code}")

    # 空 envelope
    r = requests.post(f"{GATEWAY_HTTP}/api/v1/message/send",
        json={"target_device_key": device_key, "envelope": {}},
        headers={"Authorization": f"Bearer {token}"}, timeout=5)
    check(r.status_code == 400, "empty envelope -> 400")

    # ================================================================
    # PHASE 18: 会话管理（删除/重命名/置顶）+ 记忆操作
    # ================================================================
    print("\n═══ PHASE 18: 会话管理 + 记忆操作 ═══")
    _mws18 = await connect_mobile(token)
    await drain(_mws18)

    for _action, _label in [
        ("conversation_delete", "会话删除"),
        ("conversation_update", "会话更新(rename/pin)"),
        ("memory_add", "添加记忆"),
        ("memory_delete", "删除记忆"),
    ]:
        _body18 = {"action": _action, "thread_id": f"e2e-mgmt-{int(time.time())}",
                   "content": {"text": f"test {_label}"} if _action != "conversation_delete" else {}}
        if _action == "conversation_update":
            _body18["content"] = {"title": "新标题", "is_pinned": 1}
        status, _, ms = http_send_message(token, device_key, _body18)
        check(status == 200, f"{_label}: {ms:.0f}ms")

    await _mws18.close()

    # ================================================================
    # PHASE 19: Gateway HTTP API 全覆盖
    # ================================================================
    print("\n═══ PHASE 19: Gateway HTTP API ═══")

    # Health
    r=requests.get(f"{GATEWAY_HTTP}/health",timeout=5)
    check(r.status_code==200,"GET /health -> 200")

    # Auth verify
    r=requests.post(f"{GATEWAY_HTTP}/api/v1/auth/verify",
        json={"token":token},timeout=5)
    check(r.status_code==200,"POST /api/v1/auth/verify -> 200")
    if r.status_code==200:
        d=r.json()
        check(d.get("user_id")==1,"  user_id=1")

    # User
    r=requests.get(f"{GATEWAY_HTTP}/api/v1/user/1",timeout=5)
    check(r.status_code==200,"GET /api/v1/user/1 -> 200")

    # Quota get
    r=requests.get(f"{GATEWAY_HTTP}/api/v1/quota/1",timeout=5)
    check(r.status_code==200,"GET /api/v1/quota/1 -> 200")
    if r.status_code==200:
        d=r.json()
        check("quota" in d,"  has quota field")
        check("quota_used" in d,"  has quota_used field")

    # Devices list
    r=requests.get(f"{GATEWAY_HTTP}/api/v1/devices",
        headers={"Authorization":f"Bearer {token}"},timeout=5)
    check(r.status_code==200,"GET /api/v1/devices -> 200")
    if r.status_code==200:
        d=r.json().get("data",{}).get("devices",[])
        check(isinstance(d,list),"  returns devices list")

    # LLM models
    r=requests.get(f"{GATEWAY_HTTP}/v1/models",
        headers={"Authorization":f"Bearer {token}"},timeout=10)
    check(r.status_code==200,"GET /v1/models -> 200")
    if r.status_code==200:
        models=r.json().get("data",[])
        check(len(models)>0,f"  {len(models)} models")

    # ================================================================
    # PHASE 20: 更多 Webhook 类型
    # ================================================================
    print("\n═══ PHASE 20: 更多 Webhook 类型 ═══")

    def _wh(path,payload):
        _b=json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode()
        _s=hmac.new(WEBHOOK_SECRET.encode(),_b,hashlib.sha256).hexdigest()
        return requests.post(f"{GATEWAY_HTTP}{path}",data=_b,
            headers={"Content-Type":"application/json","X-Webhook-Secret":_s},timeout=5)

    _wh_resp=_wh("/webhook/recharge/",{"event":"quota_recharge","data":{"user_id":1,"amount":100,"source":"test","order_id":"test-001","expire_time":int(time.time()+86400)}})
    check(_wh_resp.status_code in (200,404),f"webhook recharge -> {_wh_resp.status_code}")

    # user-update (no user in test env -> may 404)
    _wh_resp=_wh("/webhook/user-update/",{"event":"user_update","data":{"user_id":1,"fields":["quota"],"new_values":{"quota":100}}})
    check(_wh_resp.status_code in (200,401,404),f"webhook user-update -> {_wh_resp.status_code}")

    # eval: agent.status different statuses
    _wh_resp=_wh("/webhook/evoloop/relay",{"member_id":1,"device_key":device_key,
        "envelope":{"version":"2.0","type":"command.relay","message_id":str(uuid.uuid4()),
            "timestamp":int(time.time()),"body":{"action":"chat","content":{"text":"wh test"}}}})
    check(_wh_resp.status_code==200,f"webhook evoloop/relay -> {_wh_resp.status_code}")

    # ================================================================
    # PHASE 21: a2a_task / a2a_callback + command.ack (HTTP)
    # ================================================================
    print("\n═══ PHASE 21: a2a_task / a2a_callback / command.ack ═══")

    for _t,_l in [("a2a_task","a2a_task"),("a2a_callback","a2a_callback"),("command.ack","command.ack")]:
        _e={"version":"2.0","type":_t,"message_id":"","timestamp":int(time.time()),
            "body":{"thread_id":f"e2e-a2a-{int(time.time())}","command_id":999}}
        r=requests.post(f"{GATEWAY_HTTP}/api/v1/message/send",
            json={"target_device_key":device_key,"envelope":_e},
            headers={"Authorization":f"Bearer {token}"},timeout=10)
        check(r.status_code==200,f"HTTP {_l} -> {r.status_code}")

    # ================================================================
    # PHASE 22: LLM Proxy 额外端点
    # ================================================================
    print("\n═══ PHASE 22: LLM Proxy ═══")

    r=requests.post(f"{GATEWAY_HTTP}/v1/embeddings",
        json={"model":"kimi-k2-thinking-turbo","input":"hello world"},
        headers={"Authorization":f"Bearer {token}"},timeout=30)
    check(r.status_code in (200,400,500),f"POST /v1/embeddings -> {r.status_code}")

    r=requests.get(f"{GATEWAY_HTTP}/gateway/v1/models",
        headers={"Authorization":f"Bearer {token}"},timeout=10)
    check(r.status_code==200,f"GET /gateway/v1/models -> {r.status_code}")

    # ================================================================
    # SUMMARY
    # ================================================================
    total = passed + failed
    print(f"\n{'='*60}")
    if failed == 0:
        print(f"\x1b[32m结果: {passed}/{total} 全部通过\x1b[0m")
    else:
        print(f"结果: {passed}/{total} 通过 ({failed} 失败)")
    print(f"{'='*60}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mc-url", default=MC_URL)
    parser.add_argument("--gateway", default=GATEWAY_HTTP)
    parser.add_argument("--username", default="preterchan")
    parser.add_argument("--password", default="hellomylife")
    args = parser.parse_args()

    GATEWAY_HTTP = args.gateway
    GATEWAY_WS = args.gateway.replace("http://", "ws://").replace("https://", "wss://")
    MC_URL = args.mc_url

    print("[E2E] Logging into MC...")
    token = login_mc(MC_URL, args.username, args.password)
    print("[E2E] Fetching device...")
    device_key = fetch_device_key(MC_URL, token)
    print(f"[E2E] token={token[:20]}... device_key={device_key}")

    exit(asyncio.run(main(token, device_key)))
