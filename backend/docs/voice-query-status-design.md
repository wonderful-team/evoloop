# 状态查询设计方案

## 1. 问题

### 1.1 当前架构

```
voice.route → _handle_route()
  └─ async with lock:                           ← 锁获取
       └─ await task                            ← Supervisor → Worker → Finish 全在锁内
  ← 锁释放
```

锁在整个 Agent 执行期间不释放，第二个相同 `thread_id` 的请求被阻塞。

### 1.2 场景：用户查进度

```
第 1 轮：用户说"分析项目 A"
  → Supervisor 派 Worker（执行中，数秒~数分钟）

第 2 轮：用户说"完了吗？"
  → 新的 voice.route → 卡在锁上
  → 直到第 1 轮全部完成才进入处理
  → 但第 1 轮已经完成了，第 2 轮无意义
```

### 1.3 问题汇总

| 问题 | 影响 |
|------|------|
| 锁全程持有 | 新请求被阻塞，无法查询进度 |
| 没有Worker 状态注册表 | 不知道任务是否在运行 |
| 没有 query/new 区分 | 任何新消息都当作新指令 |
| 文字和语音各自独立 | 文字链路没有状态查询能力 |

---

## 2. 设计目标

1. **锁只覆盖快速决策阶段**，不覆盖 Worker 执行
2. **统一的Worker 状态注册表**，文字和语音共用
3. **Supervisor 自己判断 query/new**，不额外引入分类器
4. **Worker 执行中可查询进度**，不误杀旧 Worker
5. **新指令可取消旧 Worker**，行为不变

---

## 3. 架构方案

### 3.1 锁策略变更

```
改前：                                       改后：
async with lock:                             async with lock:
  L0 检查                                       L0 检查
  Supervisor 路由决策                           Supervisor 路由决策（快速）
  ├── 直接回答 → 自发布事件                       register_task()  # 注册后台
  └── route_to(worker) → Worker → Finish    ← 释放锁
                                               await task  # 锁外等待
```

锁只保护：
- L0 匹配
- Supervisor 的单次 LLM 调用（~500ms~2s）
- 任务注册

锁不保护：
- Worker 执行（数秒~数分钟）
- Finish 审计

### 3.2 Worker 状态注册表

```python
@dataclass
class WorkerRecord:
    task: asyncio.Task | None = None
    status: Literal["running", "completed", "failed", "cancelled"] = "running"
    description: str = ""           # Supervisor 的任务描述
    started_at: float = 0.0
    result: str | None = None       # 完成后的结果摘要

class WorkerRegistry:
    _tasks: dict[str, WorkerRecord]
    _lock: asyncio.Lock
```

| 阶段 | 注册表操作 |
|------|-----------|
| Supervisor 路由决策后 | `registry.register_worker(tid, task, desc)` |
| Worker/Finish 完成后 | `registry.complete_worker(tid, result)` |
| 新请求查状态 | `registry.get_worker(tid)` → 返回 WorkerRecord |
| 新指令取消旧 Worker | `registry.cancel_worker(tid)` + `task.cancel()` |

### 3.3 Supervisor 判断 query/new

Supervisor 的上下文中注入：

```
当前有正在执行的任务：[任务描述]
用户新消息：[用户输入的文本]

请判断：
1. 用户是在询问当前任务的进度或结果（query）
2. 还是想发起新的指令（new）
```

无需额外 prompt，复用现有 Supervisor 模板的 `{% if is_voice %}` 和 `{% if has_running_task %}`。

---

## 4. 完整流程

### 4.1 语音链路

```
第 1 轮：voice.route "分析项目 A"
  → _handle_route()
    → async with lock:
      → L0 检查（miss）
      → Supervisor 路由决策 → route_to(worker)
      → registry.register_worker(tid, task, "分析项目 A")
      → 释放锁
    → await task（锁外）
      → Worker 执行中...
```

```
第 2 轮：voice.route "完了吗？"
  → _handle_route()
    → async with lock:
      → registry.get_worker(tid) → status=running, desc="分析项目 A"
      → 有运行中任务
        → Supervisor 判断（含上下文和历史）
          → query → registry.get_worker(tid).result / "还在处理中"
          → new → registry.cancel_worker(tid) + 新任务
      → 释放锁
```

```
第 3 轮：voice.route "算了，查天气"
  → _handle_route()
    → async with lock:
      → registry.get_worker(tid) → status=running
      → new → registry.cancel_worker(tid) + 新任务 "查天气"
      → 释放锁
```

### 4.2 文字链路

```
POST /chat "分析项目 A"
  → dispatch_agent_run()
    → registry.register_worker(tid, task, "分析项目 A")
    → Supervisor → route_to(worker)
    → Worker 执行中...

POST /chat "完了吗？"
  → dispatch_agent_run()
    → registry.get_worker(tid) → status=running
    → Supervisor 判断 → query → 返回状态
```

---

## 5. 改动清单

### Phase 1：任务注册表 + 锁分离

| # | 文件 | 改动 |
|---|------|------|
| 1 | 新建 `app/core/engine/worker_registry.py` | `WorkerRecord` + `WorkerRegistry` |
| 2 | `voice_ws.py` | `_handle_route` 锁改为只覆盖 L0+Supervisor，`await task` 移出锁 |
| 3 | `executor.py` | 移除旧的 `_voice_tasks`/`_voice_registry`，改由 `WorkerRegistry` 替代 |
| 4 | `runner.py` | Agent 完成时更新注册表状态 |

### Phase 2：Supervisor 上下文注入

| # | 文件 | 改动 |
|---|------|------|
| 1 | `supervisor_builder.py` | 传入 `has_running_task` + `task_description` |
| 2 | `supervisor.prompt.j2` | `{% if has_running_task %}` 判断 query/new 规则 |

### Phase 3：现有路径接入

| # | 文件 | 改动 |
|---|------|------|
| 1 | `voice_ws.py` | 第 2 轮进入时调 Supervisor 判断 query/new |
| 2 | `dispatch.py` / `_chat.py` | 文字链路同路径接入注册表检查 |

---

## 6. 关键设计决策

| 决策 | 选项 | 选择理由 |
|------|------|---------|
| 谁判断 query/new？ | LLM / 规则 | **LLM（Supervisor）** — 自然语言变体太多，规则覆盖不全 |
| 注册表放在哪里？ | 全局 / 按请求 | **全局** — 文字和语音共用，跨请求可见 |
| 锁释放点？ | Supervisor 后 / Worker 后 | **Supervisor 后** — Worker 执行时间不确定，不应阻塞 |
| 旧 Worker取消方式？ | 自动 / Supervisor 决策 | **Supervisor 决策** — 让 LLM 理解用户意图后再决定 |
