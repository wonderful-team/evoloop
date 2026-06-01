"""
模拟双限 flush 策略效果：对比 naive vs 双限 的事件量和延迟分布
"""

import asyncio
import random
import time
from app.utils.token import estimate_tokens

# 双限参数
TIME_WINDOW = 1.0       # 1 秒时间窗口
TOKEN_LIMIT = 100       # 100 tokens 上限

# 模拟数据：一段典型的 LLM 长回复（~2000 tokens）
LONG_REPLY = """
当然可以。微服务架构是一种将单一应用程序划分为一组小服务的设计模式，每个服务运行在自己的进程中，
并通过轻量级机制（通常是 HTTP/REST 或消息队列）进行通信。

## 微服务的核心优势

### 1. 独立部署与扩展
每个微服务可以独立部署、升级和扩展，不影响其他服务。
这意味着团队可以按需对高频服务进行水平扩展，而不必整体扩容。

### 2. 技术栈多样性
不同的服务可以使用最适合其场景的技术栈。
例如，搜索服务可以用 Elasticsearch，推荐服务可以用 Python + ML 模型，
而用户服务可以用 Go 来获得更好的并发性能。

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

class NaiveStreamer:
    """逐 token 发布（原始方案）"""
    def stream(self, tokens: list[str]):
        events = 0
        for t in tokens:
            if t:
                events += 1
                yield t
        return events

class BatchedStreamer:
    """双限 flush 方案"""
    def __init__(self, time_window=TIME_WINDOW, token_limit=TOKEN_LIMIT):
        self._buffer = ""
        self._time_window = time_window
        self._token_limit = token_limit
        self._first_token_time = None
        self._events = 0
        self._flush_times = []

    def _should_flush(self, now) -> bool:
        if not self._buffer:
            return False
        # 条件 A: token 上限
        if estimate_tokens(self._buffer) >= self._token_limit:
            return True
        # 条件 B: 时间窗口
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
            batch = self._buffer
            self._buffer = ""
            self._first_token_time = None
            self._events += 1
            self._flush_times.append(now)
            return batch
        return None

    def flush_remaining(self, now: float):
        if self._buffer:
            batch = self._buffer
            self._buffer = ""
            self._first_token_time = None
            self._events += 1
            self._flush_times.append(now)
            return batch
        return None

def tokenize_reply(text: str) -> list[str]:
    """模拟 LLM 逐 token 输出（单词/字级别）"""
    tokens = []
    for ch in text:
        # 英文按空格分
        if ch == ' ':
            tokens.append(' ')
        elif ch == '\n':
            tokens.append('\n')
        else:
            # 模拟 token: 1-4 个字符
            if tokens and len(tokens[-1]) < 4 and tokens[-1] not in (' ', '\n'):
                tokens[-1] += ch
            else:
                tokens.append(ch)
    return tokens

def simulate(output: str, title: str):
    tokens = tokenize_reply(output)
    # 模拟时间戳：每个 token 间隔 5-50ms
    now = 0.0
    naive_count = 0
    batcher = BatchedStreamer()
    batches = []

    for t in tokens:
        now += random.uniform(0.005, 0.05)
        naive_count += 1
        batch = batcher.push(t, now)
        if batch:
            batches.append(batch)

    # flush 剩余
    remaining = batcher.flush_remaining(now)
    if remaining:
        batches.append(remaining)

    # 统计
    total_chars = len(output.strip())
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"  {'='*40}")
    print(f"  总字符数:     {total_chars}")
    print(f"  原方案事件数: {naive_count}")
    print(f"  双限事件数:   {batcher._events}")
    print(f"  压缩比:       {naive_count / max(batcher._events, 1):.1f}x")
    print(f"  batch 大小分布:")
    batch_sizes = [len(b) for b in batches]
    if batch_sizes:
        print(f"    平均: {sum(batch_sizes)/len(batch_sizes):.0f} chars")
        print(f"    最小: {min(batch_sizes)} chars")
        print(f"    最大: {max(batch_sizes)} chars")
    print(f"  首次 flush 延迟: {(batcher._flush_times[0] * 1000):.0f}ms" if batcher._flush_times else "  N/A")
    print(f"  总耗时: {(now * 1000):.0f}ms")
    print()

    return {
        "title": title,
        "naive": naive_count,
        "batched": batcher._events,
        "ratio": naive_count / max(batcher._events, 1),
        "batches": batches,
        "flush_times": batcher._flush_times,
        "total_time": now,
    }

def simulate_varied_speed(output: str, title: str):
    """模拟不同输出速度"""
    tokens = tokenize_reply(output)
    batcher = BatchedStreamer()
    now = 0.0
    batches = []

    # 前 30% 快速输出（10ms/token），后 70% 慢速（50ms/token）
    for i, t in enumerate(tokens):
        speed = 0.01 if i < len(tokens) * 0.3 else 0.05
        now += speed
        batch = batcher.push(t, now)
        if batch:
            batches.append(batch)

    remaining = batcher.flush_remaining(now)
    if remaining:
        batches.append(remaining)

    naive_count = len(tokens)
    print(f"{'='*60}")
    print(f"  {title} (变速)")
    print(f"  {'='*40}")
    print(f"  总 token 数:  {naive_count}")
    print(f"  双限事件数:   {batcher._events}")
    print(f"  压缩比:       {naive_count / max(batcher._events, 1):.1f}x")
    batch_sizes = [len(b) for b in batches]
    if batch_sizes:
        print(f"    平均: {sum(batch_sizes)/len(batch_sizes):.0f} chars")
        print(f"    最小: {min(batch_sizes)} chars")
        print(f"    最大: {max(batch_sizes)} chars")
    if batcher._flush_times:
        print(f"  首次 flush: {(batcher._flush_times[0] * 1000):.0f}ms")
        intervals = [batcher._flush_times[i+1] - batcher._flush_times[i] for i in range(len(batcher._flush_times)-1)]
        avg_interval = sum(intervals) / len(intervals) * 1000 if intervals else 0
        print(f"  平均 batch 间隔: {avg_interval:.0f}ms")
    print()

if __name__ == "__main__":
    print("=" * 60)
    print("  双限 flush 策略模拟")
    print(f"  参数: 时间窗口={TIME_WINDOW}s, Token 上限={TOKEN_LIMIT}")
    print("=" * 60)

    # 测试 1：长回答
    result1 = simulate(LONG_REPLY, "场景 1: 技术性长回复")

    # 测试 2：短回答
    simulate("好的，我来帮你看看这个问题。", "场景 2: 简短回复")

    # 测试 3：变种速度（前快后慢）
    simulate_varied_speed(LONG_REPLY, "场景 3: 变速输出")

    # 测试 4：快速连续输出（模拟流式无停顿）
    tokens = tokenize_reply(LONG_REPLY)
    batcher = BatchedStreamer()
    now = 0.0
    batches = []
    for t in tokens:
        now += 0.008  # 快节奏 8ms/token
        batch = batcher.push(t, now)
        if batch:
            batches.append(batch)
    remaining = batcher.flush_remaining(now)
    if remaining:
        batches.append(remaining)
    print(f"{'='*60}")
    print(f"  场景 4: 高速连续输出 (8ms/token)")
    print(f"  {'='*40}")
    print(f"  总 token 数:  {len(tokens)}")
    print(f"  双限事件数:   {batcher._events}")
    print(f"  压缩比:       {len(tokens) / max(batcher._events, 1):.1f}x")
    batch_sizes = [len(b) for b in batches]
    if batch_sizes:
        print(f"  平均 batch: {sum(batch_sizes)/len(batch_sizes):.0f} chars")
        print(f"  首次 flush: {(batcher._flush_times[0] * 1000):.0f}ms")
    print(f"  总耗时: {(now * 1000):.0f}ms")
    print()
