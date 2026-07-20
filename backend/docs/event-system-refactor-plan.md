# EvoLoop 事件系统统一改造方案

> 前置文档：[event-system-audit.md](./event-system-audit.md)（全量审计，含 53 个事件类、42 个订阅者、12 个问题的事实依据）
> 本文档：基于审计结论的详细改造设计，分阶段、可回滚、带验证方案

---

## 目录

1. [设计目标与原则](#一设计目标与原则)
2. [目标架构](#二目标架构)
3. [命名清理](#三命名清理)
4. [Phase 1：传输层归位](#四phase-1传输层归位)
5. [Phase 2：消灭绕过点](#五phase-2消灭绕过点)
6. [Phase 3：MessagePublisher 职责收窄](#六phase-3messagepublisher-职责收窄)
7. [Phase 4：总线语义修正](#七phase-4总线语义修正)
8. [Phase 5：Worker 接线（修 Bug）](#八phase-5worker-接线修-bug)
9. [Phase 6：Environment 总线合并（可选）](#九phase-6environment-总线合并可选)
10. [迁移顺序与回滚策略](#十迁移顺序与回滚策略)
11. [验证方案](#十一验证方案)

---

## 一、设计目标与原则

### 目标

1. **发布 API 唯一化**：事件一个入口、消息一个入口、传输层零直调。
2. **`app/core/events/` 自包含**：总线、传输、桥、schema 全部在其下，业务代码不碰传输实现。
3. **序列化契约单一**：所有 SSE 载荷经统一 envelope 构造，消灭三种并存格式。
4. **类型安全**：一切 SSE 载荷有 pydantic schema，消灭裸字符串事件与裸 `BaseEvent` 发布。

### 原则

- **事件与消息分离但各自单一路径**：事件 = 发生的"事实"（进程内 pub/sub，可公开桥接 SSE）；消息块 = 要投递的聊天内容（分发器到输出通道）。
- **不破坏现有语义**：装饰器订阅、自动发现、`sequential` 请求/响应模式（4 处在用）全部保留。
- **每阶段可独立交付、可回滚**：通过 alias / 兼容层保证中间态可用。

---

## 二、目标架构

```
                        ┌──────────────────────────────┐
                        │   app/core/events/（自包含）    │
                        │                              │
  typed event           │  system_bus（进程内 pub/sub）  │
 ──────────────────────►│      │                       │
 system_bus.publish()   │      ├─► Python 订阅者        │
                        │      └─► UniversalBridge      │  事件
                        │            （is_public 过滤）  │  系统
                        │                 │             │
                        │  EventTransport（重命名+补订阅） │◄────┘
                        │   publish + subscribe        │
                        └──────┬───────────────────────┘
                               │ chat:{tid}:events / system:events
                        ┌──────▼───────────────────────┐
                        │  app/core/engine/message/     │
                        │  MessagePublisher             │  消息
  MessageBlock          │      └─► ChannelRegistry      │  分发
 ──────────────────────►│           ├─► WebChannel ─────┼─► 同一个 Transport
                        │           └─► MobileChannel   │─► HTTP Gateway
                        └──────────────────────────────┘
                               ▲
                        stream.py 经 transport.subscribe()
                        消费（不再直调 cache.pubsub()）
```

### 分层职责（改造后）

| 层 | 组件 | 规则 |
|---|---|---|
| 事件层 | `system_bus.publish(event)` | **唯一**事件发布入口。typed `BaseEvent` 子类，`is_public` 决定是否进 SSE |
| 桥 | `UniversalBridgeSubscriber` | 唯一事件→传输的转换器，统一 envelope 构造 |
| 传输层 | `EventTransport`（改名自 `EventBus`） | `publish` + `subscribe`，**业务代码零直调** |
| 消息分发 | `MessagePublisher.publish(block)` | **只收 `MessageBlock`**，分发到 Channel |
| 通道 | WebChannel / MobileChannel | MessageBlock → 传输 / HTTP |

### 目录结构（改造后）

```
app/core/events/
├── base.py            # BaseEvent + AsyncEventBus（修语义、删死代码）
├── bus.py             # system_bus 单例
├── decorators.py      # 不变
├── discovery.py       # 删死代码
├── registry.py        # SystemEventType（补齐裸字符串类型）
├── channels.py        # 【新】频道命名：chat_events(tid) / system_events()
├── envelope.py        # 【新】统一 SSE envelope 构造
├── transport/         # 【新，从 engine/message/event_bus.py 迁入】
│   ├── base.py        # EventTransport ABC：publish + subscribe
│   ├── local.py       # in-memory
│   └── redis.py       # Redis
├── bridge.py          # UniversalBridgeSubscriber（从 subscribers/ 平移）
└── schemas/           # 事件 schema（补齐缺失导出与 typed 类）

app/core/engine/message/
└── publisher.py       # MessagePublisher：只做消息块分发
```

---

## 三、命名清理

三个 "event bus" 是当前最大的可读性障碍，优先解决。

| 现状 | 改后 | 原因 |
|---|---|---|
| `get_event_bus()` / `EventBus` | `get_event_transport()` / `EventTransport` | 它是 Redis 传输，不是事件总线 |
| awakening `event_bus` | 并入 `system_bus`（或改名 `environment_bus`） | 消除三处歧义 |
| `MessagePublisher.publish(event)` | 事件只走 `system_bus.publish()` | 职责单一 |
| `publish_custom_event("xxx")` | typed `BaseStreamEvent` 子类 | 类型安全 |

旧名保留 alias 一个版本，避免一次性改 50+ 调用点。

---

## 四、Phase 1：传输层归位

**性质**：纯基础设施，零行为变化，可独立交付。

### 1.1 移动并重命名

`app/core/engine/message/event_bus.py` → `app/core/events/transport/`

- `EventBus` ABC → `EventTransport`
- `LocalEventBus` → `LocalTransport`
- `DistributedEventBus` → `RedisTransport`
- `get_event_bus()` → `get_event_transport()`（旧名保留 alias，标记 deprecated）

### 1.2 补齐 subscribe API（解决审计问题 #3）

当前 `EventBus` ABC 只有 `publish`，订阅侧 `stream.py:45` 被迫直调 `cache.pubsub()`。补齐后传输层自成闭环：

```python
# app/core/events/transport/base.py
from contextlib import AbstractAsyncContextManager

class PubSubHandle(AbstractAsyncContextManager):
    """订阅句柄：进入即订阅，退出即退订。"""
    async def get_message(self, timeout: float = 1.0) -> str | None: ...

class EventTransport(ABC):
    @abstractmethod
    async def publish(self, channel: str, message: str) -> int: ...

    @abstractmethod
    def subscribe(self, channel: str) -> PubSubHandle: ...
```

实现映射：
- `RedisTransport.subscribe` → 包 `cache.pubsub()`（现状逻辑搬进来）
- `LocalTransport.subscribe` → 包 `in_memory_bus.subscribe()`（embedded 模式，与 publish 侧汇合于同一 `SimplePubSubBus`，对称性不变）

### 1.3 统一频道命名（解决审计问题 #2 的一部分）

新增 `app/core/events/channels.py`：

```python
def chat_events(thread_id: str) -> str:
    return f"chat:{thread_id}:events"

def system_events() -> str:
    return "system:events"
```

替换 4 处硬编码：
- `app/core/channel/web_channel.py:36,48`
- `app/core/events/subscribers/bridge.py:56-60`
- `app/core/monitoring/activity.py:430`
- `app/api/routes/stream.py:46,180`

### 1.4 stream.py 改用 transport.subscribe()

`stream.py:45` 与 `:180` 的 `cache.pubsub()` 改为 `get_event_transport().subscribe(channel)`，解除对 cache 实现的直接耦合。心跳/退避逻辑不变。

**交付物**：传输层独立、可订阅、命名统一；行为不变。

---

## 五、Phase 2：消灭绕过点

**性质**：统一序列化契约。**注意前端兼容**——typed 事件的字段需对齐现有载荷。

### 2.1 统一 envelope 契约

当前写 `chat:{tid}:events` 的三个生产者序列化各不相同。统一为：**JSON 对象，顶层必含 `type` 字段**（`stream.py:119` 的消费契约）。新增 `app/core/events/envelope.py` 集中构造，桥的 `to_frontend_payload()` 与 WebChannel 的输出都经此处校验。

### 2.2 `update_goal` 转 typed 事件（解决审计问题 #2）

`app/core/monitoring/activity.py:429` 当前裸写传输层。改为：

```python
# app/models/schemas/events.py 新增
class ActivitySnapshotEvent(BaseStreamEvent):
    type: Literal["activity"] = "activity"
    # 其余字段与现有 activity 快照对齐
```

`update_goal` 改为 `await system_bus.publish(ActivitySnapshotEvent(...))`，经桥到 SSE。前端 `event: activity` 载荷字段需逐一对照现有快照，保证兼容。

### 2.3 裸字符串 custom event 转 typed schema（解决审计问题 #9）

替换 6 处 `publish_custom_event`：

| 现状 | 新 schema |
|---|---|
| `publish_custom_event("plan.updated", {...})` ×5 | `PlanUpdatedEvent(BaseStreamEvent)`，`type="plan.updated"`，保留 `data` 字段 |
| `publish_custom_event("changeset.updated", {...})` ×1 | `ChangesetUpdatedEvent(BaseStreamEvent)`，`type="changeset.updated"` |

前端兼容：现有 WebChannel 输出 `{"type": "plan.updated", "data": {...}, "thread_id", "project_id"}`；typed 事件 `model_dump(exclude_none=True)` 需保留 `data` 与 `project_id` 字段以逐字节对齐。

### 2.4 裸 `BaseEvent` 发布转 typed schema（解决审计问题 #9）

`app/core/events/publishers.py` 里 4 个函数改为专属类：

| 函数 | 新 schema |
|---|---|
| `publish_context_polishing` | `ContextPolishingEvent` |
| `publish_config_changed` | `ConfigChangedEvent` |
| `publish_embedding_updated` | `EmbeddingUpdatedEvent` |
| `publish_skill_mutated` | `SkillMutatedEvent`（action 字段区分 create/update/delete） |

订阅者按 `event_type` 字符串匹配，类型类化后订阅侧无需改动（`@event_subscribe(SystemEventType.X)` 仍命中）。

### 2.5 裸字符串事件类型注册进 `SystemEventType`

- `subscription.changed` → `SystemEventType.SUBSCRIPTION_CHANGED`
- `system.log_entry` → `SystemEventType.LOG_ENTRY`

**交付物**：写 Redis 的生产者只剩两个（桥转事件、WebChannel 转消息块），序列化契约单一且集中。

---

## 六、Phase 3：MessagePublisher 职责收窄

**性质**：清理双人格，低风险。

### 3.1 收窄为纯消息分发器

`MessagePublisher.publish()` 只收 `MessageBlock`：
- 移除 `isinstance(payload, BaseEvent)` 分支与 `EventBase` 死类型注解
- 移除 `publish_custom_event`（随 Phase 2 删除）
- 移除 `publish_error`（审计确认仅测试用，死代码）

### 3.2 事件发布调用点迁移

经 MessagePublisher 发事件的调用点改为直接 `system_bus.publish()`：

| 文件 | 事件 |
|---|---|
| `handler/_stream_mixin.py:20,31,46` | TokenEvent / ThinkingEvent / ProgressEvent |
| `handler/_error_mixin.py:54,68,94` | QuotaExhaustedEvent / LLMAuthErrorEvent / StatusEvent |
| `api/routes/chat/scenarios.py:365,392` | QuotaExhaustedEvent / StatusEvent |

**兼容性已验证**：这些 `BaseStreamEvent` 经桥的 `to_frontend_payload()`（= `model_dump(exclude_none=True)`）与原 WebChannel 的 `to_json()`（= `model_dump_json(exclude_none=True)`）内容一致，仅 dict→JSON 时机不同，最终 Redis 载荷逐字节相同。

**交付物**：事件入口唯一（`system_bus.publish`），消息入口唯一（`MessagePublisher.publish(block)`）。

---

## 七、Phase 4：总线语义修正

**性质**：健壮性修复，需谨慎（改并发语义）。

### 4.1 实现真正的 error isolation（解决审计问题 #8）

当前 `AsyncEventBus.publish` 并发模式用 `gather(*tasks)`（`base.py:171`），`return_exceptions=False`——第一个异常照样上抛，与文档声称的 "error isolation" 矛盾。

修正：

```python
# 并发模式：隔离单个 handler 异常，汇总日志，不中断其他 handler
results = await asyncio.gather(*[h(event) for h in handlers], return_exceptions=True)
for r in results:
    if isinstance(r, Exception):
        logger.error("[EventBus] handler failed for %s: %r", type_key, r)
```

`sequential=True` / `propagate_errors=True` 的请求/响应模式（4 处：audit_service.py:291、memory/publishers.py:24、rewind.py:185、macro）保持"异常上抛"语义不变。

### 4.2 删死代码（解决审计问题 #8 + 死代码清单）

- `_lock_pool`（`base.py:99`）+ `LoopBoundResource` import
- `mark_initialized` / `is_initialized` / `handler_count` / `_initialized`
- `clear()`（生产无调用，保留测试用或移入测试工具）
- `auto_discover_all` / `reset_discovery_cache` / `get_discovered_stats`（discovery.py）
- `set_event_bus()`（transport）
- 修正文档注释

### 4.3 Rewind 订阅者去重

5 个 Rewind 类（FileRewind / MemoryRewind / TraceRewind / PlanRewind / TodoRewind）删除手动 `register(bus)` classmethod，只留 `@event_register()`（自动发现已覆盖）。

**交付物**：总线语义与文档一致，死代码清除。

---

## 八、Phase 5：Worker 接线（修 Bug）

**性质**：修正确性缺陷，高价值。

### 问题

`auto_discover_handlers()` 仅在 `app/main.py:71` 调用。Worker 进程（`bin/run_worker.py`、`scripts/run_worker.py`、`scripts/start_worker.py`）只做任务模块发现（`discover_task_modules`），**从不挂事件系统**。后果：

- `app/core/engine/tasks.py:560` 在 worker 里发 `ExtractionCompletedEvent` → 空总线，`memory` / `todo` 订阅者（memory/subscribers.py:109、todo/subscribers.py:84）**从不触发**。
- 后台任务事件（`BackgroundTaskEvent` 等）在 worker 里发布也进不了桥 → 前端收不到。

### 修复

worker 启动脚本加一行（在任务发现之后、消费之前）：

```python
from app.core.events.discovery import auto_discover_handlers
auto_discover_handlers()
```

需确认 worker 进程的 asyncio 事件循环上下文与 `LoopBoundResource` / 订阅注册兼容（`system_bus` 是模块级单例，worker 内首次 import 即创建）。

**交付物**：worker 里的事件发布与主进程行为一致。

---

## 九、Phase 6：Environment 总线合并（可选）

**性质**：简化，需评估隔离意图。

awakening `event_bus`（`environment/bus.py:17`）只有 3 个订阅者 + 桥手动跨注册（`bridge.py:32`）。其事件类型已是 `system.awakening_*` / `device.*` 命名空间，与 system_bus 无冲突。

合并后：
- environment 发布点改 `system_bus.publish()`
- 3 个 `@event_register_with_bus(event_bus)` 改 `@event_register()`
- 桥不再需要手动跨注册

**风险**：若 awakening 域有意做进程内隔离（避免高频设备事件污染全局总线），则保留独立总线但改名为 `environment_bus`。合并前需与 environment 模块负责人确认。

**交付物**（若合并）：全系统单一进程内总线。

---

## 十、迁移顺序与回滚策略

### 推荐顺序

| 阶段 | 风险 | 可独立交付 | 依赖 |
|---|---|---|---|
| Phase 1 传输层归位 | 低 | ✅ | 无 |
| Phase 5 Worker 接线 | 低 | ✅ | 无（修 Bug，优先） |
| Phase 3 MessagePublisher 收窄 | 低 | ✅ | 无（事件已可走 bus） |
| Phase 4 总线语义 | 中 | ✅ | 无 |
| Phase 2 消灭绕过点 | 中（前端兼容） | ✅ | Phase 1 |
| Phase 6 总线合并 | 中 | ✅ | 需评估 |

建议 **Phase 5 最先做**（修 Bug，零风险），**Phase 1 次之**（打地基），然后 3、4，最后 2（涉及前端兼容，需联调），6 可选。

### 回滚策略

- 所有重命名保留旧名 alias 一个版本，可整体回退 import。
- Phase 2 的 typed 事件与裸事件可并存（桥按 `is_public` + `broadcast_channel` 统一处理），逐个迁移、逐个验证，任一可单独回滚。
- 每个 Phase 独立 PR，Redis 载荷 fixture 对比作为合并门禁。

---

## 十一、验证方案

### 通用门禁（每 Phase）

1. **Redis 载荷 fixture 对比**：改造前抓取各事件类型的真实 Redis 载荷（`chat:{tid}:events` / `system:events`），改造后断言逐字节一致（字段、顺序、嵌套）。
2. **import 冒烟**：`uv run python -c "import <改动模块>"` 全通过，无循环依赖。
3. **ruff**：无新增告警。

### 分 Phase 专项

| Phase | 专项验证 |
|---|---|
| 1 | `GET /stream/chat/{tid}` 与 `/stream/system` 正常推送；embedded 与 Redis 两种模式都测 |
| 2 | 前端收到 `activity` / `plan.updated` / `changeset.updated` 事件且字段不变；对照前端消费代码 |
| 3 | token/thinking/progress/quota 事件经桥到 SSE 格式不变；消息块仍正常分发到 sse+mobile |
| 4 | 构造一个抛异常的订阅者，确认其他订阅者与调用方不受影响（error isolation 生效） |
| 5 | worker 里跑 extraction 任务，确认 memory/todo 订阅者日志出现 |
| 6 | environment 事件在合并后仍被订阅者与桥正确处理 |

### 测试基建

- 单元：mock `EventTransport`，断言桥的频道名 + envelope 结构。
- 集成：起 Redis，端到端验证 publish → bridge → subscribe → SSE 输出。
- 现有 `tests/unit/core/engine/message/test_publisher.py` 需随 Phase 3 更新（`publish_error` 删除、事件路径变更）。

---

## 附：与审计问题的对应关系

| 审计问题 # | 解决阶段 |
|---|---|
| 1 三个 event bus 命名 | 三、命名清理；Phase 6 |
| 2 三生产者三序列化 | Phase 1.3 + Phase 2 |
| 3 传输无 subscribe | Phase 1.2 |
| 4 MessagePublisher 双人格 | Phase 3 |
| 5 Worker 不挂事件系统 | Phase 5 |
| 6 SSE 有损归一化 | 单独修复（见下） |
| 7 移动回退 ③ 缺陷 | 单独修复（见下） |
| 8 publish error isolation 谎言 | Phase 4 |
| 9 裸 BaseEvent / 裸字符串类型 | Phase 2.4 / 2.5 |
| 10 /stream/system 无 event 字段 | 单独修复（见下） |
| 11 消息上云三路径 | 长期，需产品决策（本文档不展开） |
| 12 environment 私有总线 | Phase 6 |

### 顺带可修的三个独立 Bug（不属事件系统重构，但审计发现）

- **问题 #6**：`stream.py:122-125` 的 message 事件不要再走 `MessageBlockFactory.from_orm`——`data` 已是序列化好的 MessageBlock，直接透传或轻量校验即可，避免 `sequence_number→0` / `references` 丢失。
- **问题 #7**：`mobile_sync_http_task`（tasks.py:20-53）body 改为与 `_sync_mixin.sync_messages` 一致的 `{device_key, thread_id, messages: [...]}` 包裹，并走 `EvoCloudHTTPClient`（补 HMAC 签名与 token 刷新）。
- **问题 #10**：`/stream/system` 输出补 `event:` 字段，与 `/stream/chat` 对齐（需确认前端 `onmessage` 依赖）。
