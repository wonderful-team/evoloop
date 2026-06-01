"""
模拟 SSE 事件流效果：对比逐 token 发 vs 双限批量发
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
        self._flush_times = []

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
        prev_content = "".join(e["content"] for e in self._events)
        self._events.append({
            "time_ms": round(now * 1000),
            "content": self._buffer,
            "tokens": estimate_tokens(self._buffer),
            "sse_line": f'event: token\ndata: {{"type":"token","content":{repr(self._buffer[:80])}}}\n',
        })
        self._buffer = ""
        self._first_token_time = None

    def flush_remaining(self, now: float):
        if self._buffer:
            self._flush(now)

    def sse_timeline(self, title: str):
        total_tokens = estimate_tokens("".join(e["content"] for e in self._events))
        print(f"\n{'='*65}")
        print(f"  {title}")
        print(f"  {'='*50}")
        print(f"  SSE 事件流时间线 ({len(self._events)} events / ~{total_tokens} tokens):")
        print()
        for i, ev in enumerate(self._events):
            marker = "┃" if i < len(self._events) - 1 else "┗"
            content_preview = ev["content"][:60].replace("\n", "\\n")
            print(f"  {marker} T+{ev['time_ms']:5d}ms  [{ev['tokens']:3d} tok] {content_preview}")
            if i < 3 or i >= len(self._events) - 1:
                print(f"  {marker}        SSE → {ev['sse_line'][:90]}...")
            elif i == 3:
                print(f"  ┊        ... ({len(self._events)-4} more events) ...")
        print()


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


def simulate_sse(output: str, title: str, speed_range=(0.01, 0.04)):
    """模拟真实 SSE 事件流"""
    tokens = tokenize_reply(output)
    # ---- 双限方案 ----
    batcher = BatchedStreamer()
    now = 0.0
    for t in tokens:
        now += random.uniform(*speed_range)
        batcher.push(t, now)
    batcher.flush_remaining(now)

    # ---- 原始方案（仅统计） ----
    naive_count = len([t for t in tokens if t])

    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"  {'='*50}")
    print(f"  ⚡ 原始方案: {naive_count} 个 SSE 事件 (逐 token)")
    print(f"  ⚡ 双限方案: {len(batcher._events)} 个 SSE 事件")
    print(f"  ⚡ 压缩比:   {naive_count / max(len(batcher._events),1):.1f}x")
    print()

    print(f"  ┌─ SSE 事件流时间线 ────────────────────────────────────────────")
    prev_end = 0
    for i, ev in enumerate(batcher._events):
        elapsed_from_start = ev["time_ms"]
        gap = elapsed_from_start - prev_end if prev_end > 0 else 0
        prev_end = elapsed_from_start
        marker = "├" if i < len(batcher._events) - 1 else "└"
        content_preview = ev["content"][:65].replace("\n", "\\n")
        print(f"  {marker} T+{elapsed_from_start:5d}ms (+{gap:3d}ms)  [{len(ev['content']):3d}ch/{ev['tokens']:2d}tok]  {content_preview}")
        # Show SSE wire format for first 2 and last event
        if i < 2 or i >= len(batcher._events) - 2:
            truncated = ev["content"][:50]
            print(f"  │              event: token")
            print(f"  │              data: {truncated}")
    print(f"  └──────────────────────────────────────────────────────────────")
    print()


if __name__ == "__main__":
    print()
    print(f"  ╔══════════════════════════════════════════════════════════════╗")
    print(f"  ║        SSE 事件流模拟：逐 token vs 双限批量                   ║")
    print(f"  ║        时间窗口: {TIME_WINDOW}s     Token 上限: {TOKEN_LIMIT}                  ║")
    print(f"  ╚══════════════════════════════════════════════════════════════╝")

    # 场景 A: 正常速度回复
    simulate_sse(LONG_REPLY, "场景 A: 技术长回复 (25-40ms/token)", (0.025, 0.04))

    # 场景 B: 回复非常短
    simulate_sse("好的，我来帮你看看这个问题。", "场景 B: 简短回复 (10-20ms/token)", (0.01, 0.02))

    # 场景 C: 极快速度（高吞吐 LLM）
    simulate_sse(LONG_REPLY, "场景 C: 高速输出 (5-10ms/token)", (0.005, 0.01))
