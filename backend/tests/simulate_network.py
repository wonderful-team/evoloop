"""
模拟真实网络条件下 SSE 事件流：连接建立、网络抖动的效果
"""

import random
from app.utils.token import estimate_tokens

TIME_WINDOW = 1.0
TOKEN_LIMIT = 100

LONG_REPLY = """
当然可以。微服务架构是一种将单一应用程序划分为一组小服务的设计模式，每个服务运行在自己的进程中，
并通过轻量级机制进行通信。

## 微服务的核心优势

### 1. 独立部署与扩展
每个微服务可以独立部署、升级和扩展，不影响其他服务。
这意味着团队可以按需对高频服务进行水平扩展，而不必整体扩容。

### 2. 技术栈多样性
不同的服务可以使用最适合其场景的技术栈。
例如，搜索服务可以用 Elasticsearch，推荐服务可以用 Python + ML 模型。

### 3. 团队自治
每个微服务可以由独立的小团队负责，团队可以自主选择技术栈、
发布节奏和开发流程，大大减少了跨团队协调成本。

## 微服务的挑战

### 分布式系统的复杂性
服务间通过网络通信，引入了延迟、容错、分布式事务、服务发现等问题。
这些在单体架构中不存在的复杂性需要额外的基础设施投入。

### 数据一致性问题
每个服务拥有自己的数据库，跨服务的数据一致性需要使用 Saga 模式、
事件溯源等复杂的分布式事务方案。

### 运维成本
需要容器编排（Kubernetes）、服务网格、分布式追踪、集中式日志等一整套基础设施。

## 什么时候选择微服务？

微服务不适合所有场景。对于初创项目或小团队，单体架构或模块化单体通常是更好的选择。
建议在以下情况考虑微服务：
- 团队规模超过 10 人
- 应用功能模块之间有明确的边界
- 需要独立扩展不同模块
- 技术栈多样性需求强烈

总结来说，微服务是一种强大的架构模式，但它带来的复杂性需要相应的基础设施和团队成熟度来支撑。
不要为了微服务而微服务，而是当业务复杂度确实需要时才采用。
"""


class BatchedStreamer:
    def __init__(self, time_window=TIME_WINDOW, token_limit=TOKEN_LIMIT):
        self._buffer = ""
        self._time_window = time_window
        self._token_limit = token_limit
        self._first_token_time = None
        self._events = []

    def _should_flush(self, now) -> bool:
        if not self._buffer:
            return False
        if estimate_tokens(self._buffer) >= self._token_limit:
            return True
        if self._first_token_time and (now - self._first_token_time) >= self._time_window:
            return True
        return False

    def push(self, token: str, now: float):
        if not token:
            return
        if self._first_token_time is None:
            self._first_token_time = now
        self._buffer += token
        if self._should_flush(now):
            self._flush(now)

    def _flush(self, now: float):
        self._events.append({
            "backend_time_ms": round(now * 1000),
            "content": self._buffer,
            "tokens": estimate_tokens(self._buffer),
        })
        self._buffer = ""
        self._first_token_time = None

    def flush_remaining(self, now: float):
        if self._buffer:
            self._flush(now)


def tokenize_reply(text: str) -> list[str]:
    tokens = []
    for ch in text:
        if ch in (' ', '\n'):
            tokens.append(ch)
        else:
            if tokens and len(tokens[-1]) < 4 and tokens[-1] not in (' ', '\n'):
                tokens[-1] += ch
            else:
                tokens.append(ch)
    return tokens


def simulate_network(
    output: str,
    title: str,
    token_speed=(0.02, 0.04),
    sse_setup_ms=0,
    network_jitter_ms=(0, 0),
    reconnect_at_ms=None,
    reconnect_duration_ms=0,
):
    """
    模拟 SSE 事件流经过网络到达前台的过程。

    参数:
        token_speed:        LLM 每 token 生成耗时 (min, max)
        sse_setup_ms:       SSE 连接建立耗时（握手+订阅）
        network_jitter_ms:  网络传输抖动 (min, max)
        reconnect_at_ms:    断连时刻（之后的事件需等重连后才收到）
        reconnect_duration_ms: 重连耗时
    """
    tokens = tokenize_reply(output)

    # ---- 记录每个 token 的后端生成时间线（同一份） ----
    token_timeline = []  # [(backend_ms, token_text), ...]
    now = 0.0
    for t in tokens:
        now += random.uniform(*token_speed)
        token_timeline.append((now, t))

    # ---- 双限方案：批量发布 ----
    batcher = BatchedStreamer()
    for backend_now, t in token_timeline:
        batcher.push(t, backend_now)
    batcher.flush_remaining(now)

    # ---- naive 方案：逐 token 发布（同一时间线） ----
    naive_events = []
    for backend_now, t in token_timeline:
        if t:
            naive_events.append({"backend_time_ms": round(backend_now * 1000), "content": t})

    # ---- 模拟 SSE 传输到前端 ----
    def apply_network(events):
        """对一组事件施加网络条件，返回前端到达时间线"""
        frontend = []
        for ev in events:
            backend_ms = ev["backend_time_ms"]
            content_len = len(ev["content"])
            # 传输时延
            transmit_ms = content_len / 50 + random.uniform(*network_jitter_ms)
            arrival_ms = backend_ms + transmit_ms

            # SSE 连接未就绪
            if arrival_ms < sse_setup_ms:
                arrival_ms = sse_setup_ms + transmit_ms * 0.5

            # 断连重连
            if reconnect_at_ms is not None:
                reconnect_start = reconnect_at_ms
                reconnect_end = reconnect_at_ms + reconnect_duration_ms
                if reconnect_start <= backend_ms <= reconnect_end:
                    arrival_ms = reconnect_end + transmit_ms * 0.5

            frontend.append(round(arrival_ms))
        return frontend

    backend_events = batcher._events
    batched_frontend_times = apply_network(backend_events)
    naive_frontend_times = apply_network(naive_events)

    # ---- 输出 ----
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"  {'='*50}")
    print(f"  ⚡ 网络条件:")
    print(f"     - SSE 连接建立:   {sse_setup_ms}ms")
    if network_jitter_ms != (0, 0):
        print(f"     - 网络抖动:        {network_jitter_ms[0]}-{network_jitter_ms[1]}ms")
    if reconnect_at_ms:
        print(f"     - 断连时刻:        {reconnect_at_ms}ms (重连 {reconnect_duration_ms}ms)")
    print(f"  ⚡ 后端事件: {len(backend_events)} 个 (naive={len(naive_events)})")
    print()

    # 后端 vs 前端时间线对比
    print(f"  ┌─ 后端 → 前端 时间线 ────────────────────────────────────")
    for i, ev in enumerate(backend_events):
        marker = "├" if i < len(backend_events) - 1 else "└"
        chars = len(ev["content"])
        preview = ev["content"][:50].replace("\n", "\\n")
        arrival = batched_frontend_times[i]

        print(f"  {marker} 后端 T+{ev['backend_time_ms']:5d}ms  [{chars:3d}ch]  {preview}")
        print(f"  │  前端 T+{arrival:5d}ms")
        print(f"  │")
    print(f"  └───────────────────────────────────────────────────────")

    # 关键指标
    if batched_frontend_times:
        first_arrival = batched_frontend_times[0]
        last_arrival = batched_frontend_times[-1]
        print(f"\n  📊 前端体验指标:")
        print(f"     - 首字显示:       T+{first_arrival:5d}ms  (naive: T+{naive_frontend_times[0]:5d}ms)")
        print(f"     - 完成时间:       T+{last_arrival:5d}ms  (naive: T+{naive_frontend_times[-1]:5d}ms)")
        print(f"     - 展现总耗时:     {last_arrival - first_arrival}ms  (naive: {naive_frontend_times[-1] - naive_frontend_times[0]}ms)")
        print(f"     - 平均 batch 间隔: {(last_arrival - first_arrival) / max(len(batched_frontend_times)-1, 1):.0f}ms")
    print()


if __name__ == "__main__":
    print()
    print(f"  ╔══════════════════════════════════════════════════════════╗")
    print(f"  ║    SSE 网络模拟：连接建立/抖动/断连对事件流的影响        ║")
    print(f"  ║    双限参数: 时间窗口={TIME_WINDOW}s  Token上限={TOKEN_LIMIT}         ║")
    print(f"  ╚══════════════════════════════════════════════════════════╝")

    # 场景 1：理想网络，无延迟
    simulate_network(LONG_REPLY, "场景 1: 理想网络（无额外延迟）")

    # 场景 2：SSE 连接建立耗时 800ms
    simulate_network(
        LONG_REPLY, "场景 2: SSE 连接慢 (800ms)",
        sse_setup_ms=800,
    )

    # 场景 3：SSE 连接极慢 + 网络抖动
    simulate_network(
        LONG_REPLY, "场景 3: 网络差 (连接1.5s + 抖动50-150ms)",
        sse_setup_ms=1500,
        network_jitter_ms=(50, 150),
    )

    # 场景 4：中间断连一次，重连 2s
    simulate_network(
        LONG_REPLY, "场景 4: 中间断连 (3s 时掉线, 重连 2s)",
        reconnect_at_ms=3000,
        reconnect_duration_ms=2000,
    )

    # 场景 5：极慢 LLM + 慢连接
    simulate_network(
        LONG_REPLY, "场景 5: LLM 慢 (50-80ms/token) + SSE 连接 500ms",
        token_speed=(0.05, 0.08),
        sse_setup_ms=500,
    )
