#!/usr/bin/env python3
"""
EvoLoop 对话客户端（供 Agent/脚本持续使用）

功能：
  - 发消息前自动登录（凭据来自环境变量或 ~/.evoloop_chat.conf）
  - 固定使用 project_id=120
  - 持久化 thread_id（同一会话续聊，--new-thread 开启新会话）
  - 通过 SSE 流式打印 EvoLoop 的回复与过程
  - HITL 支持：SSE 收到 human_request 事件时自动批准/拒绝（--approve / --reject）

用法：
  evoloop_chat.py -m "你的消息"
  evoloop_chat.py -m "你的消息" --new-thread
  evoloop_chat.py -m "你的消息" --verbose
  evoloop_chat.py -m "你的消息" --diagnose   # 消息跑完后输出 Agent 行为诊断（节点流转 / Worker 派发次数 / 重复派发检测）
  evoloop_chat.py -m "你的消息" --approve    # 自动批准所有待审批请求（默认即此行为）
  evoloop_chat.py -m "你的消息" --no-approve # 不自动批准，HITL 请求停留等待人工
  evoloop_chat.py -m "你的消息" --reject     # 所有待审批请求自动拒绝

配置（环境变量或配置文件 ~/.evoloop_chat.conf 每行 key=value）：
  EVOLOOP_API=http://127.0.0.1:20160
  EVOLOOP_USERNAME=xxx
  EVOLOOP_PASSWORD=xxx
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger("evoloop_chat")

CONFIG_PATH = Path.home() / ".evoloop_chat.conf"
STATE_PATH = Path.home() / ".evoloop_chat.state.json"
DEFAULT_API = "http://127.0.0.1:20160"
DEFAULT_PROJECT_ID = 120


def load_config() -> dict:
    cfg = {
        "EVOLOOP_API": os.environ.get("EVOLOOP_API", DEFAULT_API),
        "EVOLOOP_USERNAME": os.environ.get("EVOLOOP_USERNAME", "preterchan"),
        "EVOLOOP_PASSWORD": os.environ.get("EVOLOOP_PASSWORD", "hellomylife"),
    }
    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            if k in cfg and not os.environ.get(k):
                cfg[k] = v
    return cfg


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def http_json(url: str, data=None, headers=None, method=None, timeout: int = 60):
    req = urllib.request.Request(url, headers=headers or {}, method=method or ("GET" if data is None else "POST"))
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, body, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return resp.status, raw


def login(cfg: dict) -> str:
    username = cfg["EVOLOOP_USERNAME"]
    password = cfg["EVOLOOP_PASSWORD"]
    if not username or not password:
        raise SystemExit(
            f"[错误] 缺少登录凭据，请在 {CONFIG_PATH} 或环境变量中配置 EVOLOOP_USERNAME / EVOLOOP_PASSWORD"
        )
    url = f"{cfg['EVOLOOP_API'].rstrip('/')}/api/v1/login/access-token"
    status, raw = http_json(url, data={"username": username, "password": password}, timeout=60)
    try:
        data = json.loads(raw)
    except Exception:
        raise SystemExit(f"[错误] 登录响应解析失败 (HTTP {status}): {raw[:200]}")
    token = data.get("access_token")
    if status != 200 or not token:
        raise SystemExit(f"[错误] 登录失败: {json.dumps(data, ensure_ascii=False)[:300]}")
    return token


def get_token(cfg: dict, state: dict, verbose: bool = False) -> str:
    token = state.get("token")
    if token:
        return token
    if verbose:
        print("[登录] 未找到 token，开始登录...", flush=True)
    token = login(cfg)
    state["token"] = token
    save_state(state)
    return token


_HITL_CTX = {"mode": None, "cfg": None, "token": None, "thread_id": None}


def resume_hitl(decision: str) -> bool:
    """批准/拒绝当前挂起的 HITL 请求（POST /chat/resume）。

    decision 归一化由后端 normalize_hitl_input 处理（yes→APPROVED / no→REJECTED）。
    """
    cfg = _HITL_CTX["cfg"]
    token = _HITL_CTX["token"]
    thread_id = _HITL_CTX["thread_id"]
    url = f"{cfg['EVOLOOP_API'].rstrip('/')}/api/v1/chat/resume"
    body = json.dumps({
        "thread_id": thread_id,
        "user_input": decision,
        "model": "",
        "project_id": DEFAULT_PROJECT_ID,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
        result = json.loads(raw)
        if result.get("status") == "resuming":
            print(f"\n[HITL] 已{decision}，等待重执行...", flush=True)
            return True
        print(f"\n[HITL] resume 响应异常: {raw[:200]}", flush=True)
        return False
    except Exception as e:
        print(f"\n[HITL] resume 失败: {e}", file=sys.stderr, flush=True)
        return False


def send_message(cfg: dict, token: str, message: str, thread_id: str, project_id: int, skill_ids: list[int] | None = None, working_directory: str | None = None, host_context: dict | None = None, model: str | None = None) -> None:
    url = f"{cfg['EVOLOOP_API'].rstrip('/')}/api/v1/chat"
    body = {
        "message": message,
        "thread_id": thread_id,
        "project_id": project_id,
    }
    # 审计修正：不带 model 会走网关默认路由（实测对无 model 请求会长时间
    # 挂起）——与前端 selectedModel 行为对齐，默认 deepseek-v4-flash。
    body["model"] = model or "deepseek-v4-flash"
    if skill_ids:
        body["skill_ids"] = skill_ids
    if working_directory:
        body["working_directory"] = working_directory
    if host_context:
        body["host_context"] = host_context
    body_bytes = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body_bytes,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    result = json.loads(raw)
    if result.get("status") == "done":
        print(json.dumps(result, ensure_ascii=False))
        return
    if result.get("status") != "queued":
        raise SystemExit(f"[错误] 发送消息失败: {raw[:300]}")


def stream_reply(cfg: dict, token: str, thread_id: str, state: dict, verbose: bool = False) -> None:
    url = f"{cfg['EVOLOOP_API'].rstrip('/')}/api/v1/stream/chat/{urllib.parse.quote(thread_id)}"
    seq_key = f"last_seq:{thread_id}"
    headers = {"Authorization": f"Bearer {token}"}
    # Last-Event-ID 断点续传：跳过上一轮已消费的缓冲事件（旧 run 的终态
    # 重放会把"上一次的 cancelled"误当成本轮结果）。
    after_seq = state.get(seq_key)
    if after_seq is not None:
        headers["Last-Event-ID"] = str(after_seq)
    req = urllib.request.Request(url, headers=headers)
    event_name = None
    current_seq = None
    buffer = ""
    deadline = time.time() + 600
    done_at = None
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            for raw_line in resp:
                if time.time() > deadline:
                    print("\n[超时] 会话处理超过 600 秒，已停止等待（会话仍在后台继续）", flush=True)
                    return
                if done_at is not None and time.time() - done_at >= 3:
                    return
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                if line == "":
                    event_data = buffer.strip()
                    buffer = ""
                    if event_data:
                        handle_event(event_name, event_data, verbose)
                        if current_seq:
                            state[seq_key] = int(current_seq)
                        if _STREAM_PRINTED["run_done"] and done_at is None:
                            done_at = time.time()
                        if _STREAM_PRINTED["resumed"]:
                            _STREAM_PRINTED["resumed"] = False
                            done_at = None
                    event_name = None
                    continue
                if line.startswith("event:"):
                    event_name = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    buffer += line[len("data:"):].strip()
                elif line.startswith("id:"):
                    current_seq = line[len("id:"):].strip()
                elif line.startswith(":"):
                    continue  # 心跳
                elif line.strip():
                    # 审计修正：未知行不得拼进 data buffer（id: 行曾落此分支
                    # 导致 json.loads 失败、全部事件被静默丢弃）
                    logger.warning(f"[stream] unrecognized SSE line: {line[:40]}")
    except urllib.error.HTTPError as e:
        print(f"[错误] 流式读取失败: HTTP {e.code}", file=sys.stderr)
        if e.code == 401:
            raise SystemExit("[错误] token 失效，请重新配置并删除状态文件后重试")


_STREAM_PRINTED = {"content": False, "last": "", "token_buf": "", "run_done": False, "resumed": False}


def handle_event(event_name: str, data: str, verbose: bool) -> None:
    try:
        obj = json.loads(data)
    except Exception:
        return
    etype = obj.get("type", event_name)

    if etype == "activity":
        agent_state = obj.get("agent_state") or {}
        mode = agent_state.get("mode")
        task = agent_state.get("task_name") or agent_state.get("task_status") or ""
        final = obj.get("final_outcome")
        if final:
            _STREAM_PRINTED["run_done"] = True
        if verbose or final:
            if final:
                print(f"\n[完成] final_outcome = {final}", flush=True)
            elif mode:
                print(f"[进度] mode={mode} task={task}", flush=True)
    elif etype in ("run_end", "session_completed"):
        _STREAM_PRINTED["run_done"] = True
        final = obj.get("final_outcome") or (obj.get("data") or {}).get("final_outcome")
        print(f"\n[完成] {final or obj.get('status') or 'done'}", flush=True)
    elif etype == "message":
        # message 事件 = 落库完整消息。token 流式已展示 LLM 实时文本（主观测），
        # 这里补充展示结构化信息：工具调用/结果（token 流里没有）、以及
        # 未被 token 覆盖的文本（如最终报告、Worker 总结）。
        data = obj.get("data") or obj
        content = data.get("content") or ""
        role = data.get("role", "")
        category = data.get("category", "")
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        text = (text or "").strip()
        token_buf = _STREAM_PRINTED.get("token_buf", "")

        if role == "tool" and text:
            # 工具执行结果：token 流里没有，补充展示
            print(f"\n[工具] {text[:200]}", flush=True)
        elif role == "ai":
            if text and text not in token_buf:
                # 文本未被 token 流覆盖（如 Worker 最终报告）→ 打印
                if text != _STREAM_PRINTED["last"]:
                    _STREAM_PRINTED["last"] = text
                    _STREAM_PRINTED["content"] = True
                    print(f"\n{text}", flush=True)
            elif category == "assistant_response":
                # 最终回复若已被 token 覆盖，token 流已显示，无需重复
                pass
            # 工具调用（route_to 等）通过 verbose 的原始事件展示
    elif etype == "token":
        tok = obj.get("content", "") or ""
        if tok:
            _STREAM_PRINTED["token_buf"] = (_STREAM_PRINTED.get("token_buf", "") + tok)[-8000:]
            print(tok, end="", flush=True)
    elif etype == "human_request":
        print(f"\n[待审批] {json.dumps(obj, ensure_ascii=False)[:300]}", flush=True)
        # 仅对 create（真正的审批请求）自动批准/拒绝；clear 等生命周期事件
        # 是前端清卡片信号，对其 resume 会被当成"新消息"注入（双发根因）。
        if obj.get("action", "create") != "create":
            return
        mode = _HITL_CTX["mode"]
        if mode:
            decision = "yes" if mode == "approve" else "no"
            if resume_hitl(decision):
                _STREAM_PRINTED["resumed"] = True
    elif etype == "error":
        print(f"\n[错误] {obj.get('error', obj)}", flush=True)
    elif verbose:
        print(f"[{etype}] {json.dumps(obj, ensure_ascii=False)[:200]}", flush=True)


def fetch_reply(cfg: dict, token: str, thread_id: str, verbose: bool = False) -> None:
    """兜底：从会话消息接口拉取 AI 最终回复（SSE 流可能漏事件时用）。"""
    if _STREAM_PRINTED["content"] and not verbose:
        return
    url = f"{cfg['EVOLOOP_API'].rstrip('/')}/api/v1/conversations/{urllib.parse.quote(thread_id)}/messages"
    try:
        status, raw = http_json(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if status != 200:
            return
        data = json.loads(raw)
        msgs = data.get("data") if isinstance(data, dict) else data
        if isinstance(msgs, dict):
            msgs = msgs.get("messages", msgs.get("list", []))
        if not isinstance(msgs, list):
            return
        printed = 0
        for m in msgs:
            if m.get("role") == "ai" and m.get("content"):
                content = m["content"]
                if isinstance(content, str):
                    print(f"\n[回复] {content}", flush=True)
                printed += 1
        if verbose:
            print(f"[消息] 会话共 {len(msgs)} 条，AI 回复 {printed} 条", flush=True)
    except Exception as e:
        if verbose:
            print(f"[消息] 拉取失败: {e}", file=sys.stderr, flush=True)


def fetch_all_messages(cfg: dict, token: str, thread_id: str) -> list:
    """拉取会话全部可见消息（含 node_source / category / sequence_number）。"""
    url = f"{cfg['EVOLOOP_API'].rstrip('/')}/api/v1/conversations/{urllib.parse.quote(thread_id)}/messages?limit=100"
    try:
        status, raw = http_json(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if status != 200:
            return []
        data = json.loads(raw)
        msgs = data.get("data") if isinstance(data, dict) else data
        if isinstance(msgs, dict):
            msgs = msgs.get("messages", msgs.get("list", []))
        if not isinstance(msgs, list):
            return []
        return [m for m in msgs if isinstance(m, dict)]
    except Exception as e:
        print(f"[诊断] 拉取消息失败: {e}", file=sys.stderr, flush=True)
        return []


def diagnose_thread(cfg: dict, token: str, thread_id: str) -> None:
    """行为诊断：分析会话消息，输出节点流转 / Worker 派发次数 / 重复派发检测。

    用于验证 Agent 修复后的行为是否符合预期，重点观察：
      - Worker 是否被重复派发执行同一个任务（修复目标：只执行一次）；
      - Supervisor 是否在 Worker 完成后正确收尾（vs 反复 route_to）；
      - 各节点的消息数量与流转是否合理。
    """
    msgs = fetch_all_messages(cfg, token, thread_id)
    if not msgs:
        print("[诊断] 无消息可分析（可能会话尚未结束或接口异常）。", flush=True)
        return

    def _seq(m):
        return m.get("sequence_number") or 0

    msgs.sort(key=_seq)

    print("\n" + "=" * 60, flush=True)
    print("[Agent 行为诊断]", flush=True)
    print(f"消息总数: {len(msgs)}", flush=True)

    # 1. 节点流转概览（按 node_source 统计）
    node_counts: dict[str, int] = {}
    for m in msgs:
        ns = m.get("node_source") or "-"
        node_counts[ns] = node_counts.get(ns, 0) + 1
    print(f"节点分布: {node_counts}", flush=True)

    # 2. 按 sequence 输出精简流转线（human / supervisor / worker / finish / tool）
    flow = []
    for m in msgs:
        role = m.get("role", "")
        ns = m.get("node_source") or ""
        category = m.get("category") or ""
        if role == "human":
            flow.append(f"seq{m.get('sequence_number')}:HUMAN")
        elif role == "ai" and ns == "supervisor":
            flow.append(f"seq{m.get('sequence_number')}:SUPERVISOR")
        elif role == "ai" and ns == "worker":
            flow.append(f"seq{m.get('sequence_number')}:WORKER")
        elif role == "ai" and ns == "finish":
            flow.append(f"seq{m.get('sequence_number')}:FINISH")
        elif role == "tool":
            flow.append(f"seq{m.get('sequence_number')}:TOOL({category or ns})")
    print(f"流转线: {' -> '.join(flow) if flow else '(空)'}", flush=True)

    # 3. 检测 Worker 派发次数。
    #    route_to 是内部信号不落库，且 Supervisor 轮间可能无可见 assistant 消息，
    #    因此"连续 worker 消息段"并不可靠。改用更稳的信号：
    #      - worker 节点的 assistant_response（最终报告）条数 = Worker 完成次数；
    #      - worker 节点首次工具调用的时间跨度；以及工具调用总量（重复派发会翻倍）。
    worker_segments = 0
    prev_worker = False
    worker_tool_calls = 0
    worker_reports = 0
    worker_tool_seq: list[int] = []
    for m in msgs:
        ns = m.get("node_source") or ""
        role = m.get("role", "")
        if ns == "worker":
            if not prev_worker:
                worker_segments += 1
            prev_worker = True
            if role == "ai" and m.get("category") == "assistant_response":
                worker_reports += 1
            if role == "tool":
                worker_tool_calls += 1
                worker_tool_seq.append(m.get("sequence_number") or 0)
        else:
            prev_worker = False

    print(f"Worker 执行段数(粗略): {worker_segments}", flush=True)
    print(f"Worker 工具调用数: {worker_tool_calls}", flush=True)
    print(f"Worker 最终报告数: {worker_reports}", flush=True)

    # 重复派发核心信号：一个任务若有 >1 次 Worker 最终报告（assistant_response），
    # 说明同一个任务被执行了多遍。
    if worker_reports > 1:
        print(f"⚠️  [异常] Worker 报告 {worker_reports} 次（同一任务疑似被执行多遍）", flush=True)
    elif worker_segments > 1:
        print(f"⚠️  [异常] Worker 执行段 {worker_segments} 段（同一任务疑似重复派发）", flush=True)
    else:
        print("✅ Worker 只执行 1 次（符合预期）", flush=True)

    # 4. Supervisor 收尾检测：最后一条 AI 消息是否来自 supervisor 且为 assistant_response
    last_ai = None
    for m in reversed(msgs):
        if m.get("role") == "ai":
            last_ai = m
            break
    if last_ai:
        last_ns = last_ai.get("node_source") or "-"
        last_cat = last_ai.get("category") or ""
        last_content = (last_ai.get("content") or "")[:120]
        print(f"最后 AI 消息: node={last_ns} category={last_cat}", flush=True)
        print(f"  内容: {last_content}", flush=True)
        if last_ns == "supervisor" and last_cat == "assistant_response":
            print("✅ Supervisor 正常收尾（直接回答用户）", flush=True)
        elif last_ns == "worker":
            print("⚠️  以 Worker 报告结尾，Supervisor 可能未完成收尾", flush=True)
        else:
            print(f"ℹ️  以 {last_ns} 结尾", flush=True)

    # 5. 重复派发证据：相邻 Worker 段之间是否夹着 supervisor 的 route（无实际回复）
    print("=" * 60, flush=True)


def main():
    parser = argparse.ArgumentParser(description="EvoLoop 对话客户端")
    parser.add_argument("-m", "--msg", dest="message", help="消息对话内容")
    parser.add_argument("--new-thread", action="store_true", help="开启新的会话线程")
    parser.add_argument("--verbose", action="store_true", help="打印过程事件")
    parser.add_argument("--project-id", type=int, default=None, help="指定 project_id（默认 120）")
    parser.add_argument("--skill-ids", type=int, nargs="+", default=None, help="指定要挂载的 skill id 列表，如 --skill-ids 12")
    parser.add_argument("--working-directory", type=str, default=None, help="指定线程工作目录（会影响相对路径读写）")
    parser.add_argument("--host-context", type=str, default=None, help="JSON, e.g. {" + chr(34) + "domain" + chr(34) + ":...}")
    parser.add_argument("--diagnose", action="store_true", help="消息跑完后输出 Agent 行为诊断（节点流转 / Worker 派发次数 / 重复派发检测）")
    parser.add_argument("--model", type=str, default=None, help="指定模型（默认 deepseek-v4-flash，与前端 selectedModel 对齐）")
    decision = parser.add_mutually_exclusive_group()
    decision.add_argument("--approve", action="store_true", help="自动批准所有 HITL 待审批请求（默认行为）")
    decision.add_argument("--no-approve", action="store_true", help="不自动批准，HITL 请求停留等待人工处理")
    decision.add_argument("--reject", action="store_true", help="自动拒绝所有 HITL 待审批请求")
    args = parser.parse_args()

    if not args.message:
        raise SystemExit("用法: evoloop_chat.py -m \"你的消息\" [--new-thread]")

    cfg = load_config()
    state = load_state()

    token = get_token(cfg, state, args.verbose)

    project_id = args.project_id if args.project_id is not None else state.get("project_id", DEFAULT_PROJECT_ID)
    state["project_id"] = project_id
    if args.new_thread or not state.get("thread_id"):
        thread_id = f"cli-{int(time.time())}-{os.getpid()}"
        state["thread_id"] = thread_id
        save_state(state)
        if args.verbose:
            print(f"[会话] 新建 thread_id = {thread_id}", flush=True)
    else:
        thread_id = state["thread_id"]
        if args.verbose:
            print(f"[会话] 继续 thread_id = {thread_id}", flush=True)

    # 默认自动批准（保证值守/巡检流程不因 HITL 卡住）；--no-approve / --reject 覆盖。
    mode = "approve"
    if args.reject:
        mode = "reject"
    elif args.no_approve:
        mode = None
    _HITL_CTX.update({
        "mode": mode,
        "cfg": cfg,
        "token": token,
        "thread_id": thread_id,
    })

    host_ctx = None
    if args.host_context:
        import json as _json
        host_ctx = _json.loads(args.host_context)
    send_message(cfg, token, args.message, thread_id, project_id, args.skill_ids, args.working_directory, host_ctx, model=args.model)
    stream_reply(cfg, token, thread_id, state, args.verbose)
    save_state(state)
    fetch_reply(cfg, token, thread_id, args.verbose)
    if args.diagnose:
        diagnose_thread(cfg, token, thread_id)


if __name__ == "__main__":
    main()
