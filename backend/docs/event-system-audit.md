# EvoLoop 事件与消息系统 — 全量审计

> 审计对象：`evoloop/backend/app/`
> 范围：事件定义 / 事件发布 / 事件订阅 / SSE / WebChannel / MobileChannel / 消息同步 / 死代码
> 目的：为事件订阅与发布系统的统一改造提供事实依据

---

## 目录

1. [总体架构](#一总体架构实际现状)
2. [事件定义全表](#二事件定义全表53-个事件类)
3. [订阅者全表](#三订阅者全表42-个类)
4. [SSE 层](#四sse-层apiroutesstreampy)
5. [WebChannel](#五webchannelcorechannelweb_channelpy)
6. [MobileChannel](#六mobilechannelcorechannelmobile_channelpy)
7. [消息同步三条路径](#七消息同步同一份数据上云有三条路径)
8. [死代码总清单](#八死代码总清单)
9. [问题总清单](#九问题总清单改造依据)

---

## 一、总体架构（实际现状）

系统里存在 **三层基础设施**，但边界不清、命名冲突、存在多处绕过。

```
┌─ 事件系统（typed 事件）────────────────────────────────────────┐
│                                                                 │
│  发布点（50+ 处）                                                │
│    └─► system_bus.publish(event)     environment/event_bus      │
│              │  （42 个 Python 订阅者）  （3 个订阅者）           │
│              │                          │                       │
│              └────┬─────────────────────┘                       │
│                   ▼                                             │
│        UniversalBridgeSubscriber（唯一 @event_subscribe_all）     │
│            is_public=True 的事件 → to_frontend_payload()        │
│                   │                                             │
├─ 消息分发（MessageBlock）──────────────┐                        │
│    MessagePublisher.publish(block)     │                        │
│      └─► ChannelRegistry               │                        │
│            ├─► WebChannel("sse") ──────┼────┐                   │
│            └─► MobileChannel("mobile") │    │                   │
│                   │                    │    ▼                   │
│                   │            HTTP → Gateway → MC              │
├─ 传输层 ──────────┼────────────────────┼────────────────────────┘
│   get_event_bus() ◄┘  （ABC 只有 publish，没有 subscribe）
│     LocalEventBus（内存）/ DistributedEventBus（Redis）
│              │
│              ▼  chat:{tid}:events / system:events
├─ 消费层 ────────────────────────────────────────────┐
│   GET /stream/chat/{tid}   ← cache.pubsub()（绕过传输抽象）
│   GET /stream/system       ← cache.pubsub()
└──────────────────────────────────────────────────────┘
```

### 三层基础设施清单

| 层 | 组件 | 位置 | 职责 |
|---|---|---|---|
| L1 进程内总线 | `system_bus`（单例 `SystemEventBus`） | `app/core/events/base.py:213` | typed 事件 pub/sub，42 个订阅者类 |
| L1 进程内总线 | `event_bus`（awakening 域私有，非单例） | `app/core/environment/bus.py:17` | environment 域内部编排，3 个订阅者 |
| L2 桥接 | `UniversalBridgeSubscriber` | `app/core/events/subscribers/bridge.py` | `is_public=True` 事件 → Redis SSE |
| L3 外部传输 | `EventBus` ABC → `LocalEventBus`/`DistributedEventBus` | `app/core/engine/message/event_bus.py` | Redis/内存 pub-sub，**只有 publish，没有 subscribe** |
| 消息分发 | `MessagePublisher` + `ChannelRegistry` | `app/core/engine/message/publisher.py`、`app/core/channel/` | MessageBlock 多端投递 |

### 关键机制

- **订阅注册**：`@event_subscribe(type)` / `@event_subscribe_all()` 标记方法；`@event_register()` 装饰类，在实例化时经 `register_instance_handlers` 注册到总线。
- **自动发现**：`auto_discover_handlers()`（`app/core/events/discovery.py:155`）启动时递归扫描 `app.core` / `app.domain` / `app.infrastructure`，实例化带 `_auto_register` 标记的类。**仅在 `app/main.py:71` 调用一次。**
- **桥接**：`UniversalBridgeSubscriber` 是唯一 `@event_subscribe_all` 订阅者，同时手动注册到 awakening 总线（`bridge.py:32`）。`is_public=True` 的事件经 `to_frontend_payload()` 序列化后写入 Redis 频道。
- **启动序列**（`app/main.py` lifespan）：DB 初始化 → `register_default_channels()` → godcmd → memory → **`auto_discover_handlers()`** → `publish_app_started()`。

---

## 二、事件定义全表（53 个事件类）

图例：
- ✅ **完整链路**（有发布有订阅）
- 📡 **仅前端**（无 Python 订阅者，经桥到 SSE）
- ❌ **死代码**

### 2.1 核心生命周期（`app/core/events/schemas/lifecycle.py`）

| 事件 | event_type | public/channel | 发布 | 订阅 | 状态 |
|---|---|---|---|---|---|
| SessionCompletedEvent | system.session_completed | T/chat | finish.py:262 | monitoring:27, learning:124, routing:36+103 | ✅ |
| ExtractionRequestedEvent | system.extraction_requested | F | audit_service.py:290 | todo:43, memory:52 | ✅ |
| ExtractionCompletedEvent | system.extraction_completed | F | tasks.py:560 | todo:84, memory:109 | ✅ |
| SystemStatusEvent | system.state_refreshed | T/chat | activity.py ×4 | 仅桥 | 📡 |
| AppStartedEvent | system.app_started | T/system | main.py:79 | 10 个订阅者 | ✅ |
| AppStoppingEvent | system.app_stopping | T/system | main.py:101 | 7 个订阅者 | ✅ |
| UserLoggedInEvent | system.user_logged_in | T/system | account.py ×3 | evocloud:69, project:161, benefits:19 | ✅ |
| UserLoggedOutEvent | system.user_logged_out | T/system | account.py:290 | evocloud:78, benefits:26 | ✅ |
| SubscriptionChangedEvent | `subscription.changed`（裸字符串） | T/system | subscription.py:116 | 无 | 📡 |
| SystemLogEvent | `system.log_entry`（裸字符串） | T/chat | activity.py:375 | 无 | 📡 |

### 2.2 流式事件（`app/models/schemas/events.py`，全部 public/chat，前端消费）

| 事件 | type | 发布 | 状态 |
|---|---|---|---|
| TokenEvent | token | handler/_stream_mixin.py:20 | 📡 |
| ThinkingEvent | thinking | handler/_stream_mixin.py:31 | 📡 |
| ProgressEvent | progress | handler/_stream_mixin.py:46 | 📡 |
| StatusEvent | status | handler/_error_mixin.py:94, scenarios.py:392 | 📡 |
| ArtifactEvent | artifact | activity.py:402 | 📡 |
| AgentStateEvent | agent_state | activity.py:349 | 📡 |
| MessageSyncEvent | message | mapper.py:254（仅 WebChannel 用，不经总线） | 📡 |
| HumanRequestEvent | human_request | activity.py ×3 | 📡 |
| QuotaExhaustedEvent | quota_exhausted | errors.py:90, _error_mixin.py:54, scenarios.py:365 | 📡 |
| AuthExpiredEvent | auth_expired | errors.py:62 | 📡 |
| LLMAuthErrorEvent | llm_auth_error | errors.py:76, _error_mixin.py:68 | 📡 |
| **RunStartEvent** | run_start | **从不实例化**（前端的 run_start 由 AgentSessionStartedEvent 映射） | ❌ |
| **RunEndEvent** | run_end | **从不实例化**（同上，由 AgentRunCompletedEvent 映射） | ❌ |

### 2.3 Agent 引擎事件（`app/core/engine/event/schemas.py`）

| 事件 | event_type | public/channel | 发布 | 订阅 | 状态 |
|---|---|---|---|---|---|
| AgentSessionStartedEvent | system.session_started | T/chat | activity.py:148 | project:382 | ✅ |
| AgentRunCompletedEvent | agent.run_completed | T/chat | activity.py:164, runner.py:165 | routing:48, evocloud:114 | ✅ |
| WebSocketMessageReceivedEvent | websocket.message_received | F | websocket_link.py:540 | engine:80, project:44 | ✅ |
| ConversationDeletedEvent | conversation.deleted | F | subscribers.py:170, _conversations.py:128 | engine:586, context:40, memory:382, learning:277 | ✅ |

### 2.4 工具 / Rewind 事件

| 事件 | event_type | 发布 | 订阅 | 状态 |
|---|---|---|---|---|
| BackgroundTaskEvent | tool.background_task_updated | tools/background/manager.py:481 | 无 | 📡 |
| BackgroundTaskOutputEvent | tool.background_task_output | tools/background/manager.py:502 | 无 | 📡 |
| RewindRequestedEvent | rewind.requested | engine/rewind/rewind.py:174 | planning:42, todo:203, file:35, memory:170, learning:183 | ✅ |
| MessagesCleanupEvent | rewind.messages.cleanup | engine/rewind/rewind.py:119 | evocloud:219 | ✅ |

### 2.5 Project / Codebase / 其他域事件

| 事件 | event_type | 发布 | 订阅 | 状态 |
|---|---|---|---|---|
| ProjectCreatedEvent | project.created | sync_service ×2, watchers | codebase:156, project:124 | ✅ |
| ProjectDeletedEvent | project.deleted | sync_service, watchers | codebase:181, project:132 | ✅ |
| ProjectMovedEvent | project.moved | watchers | codebase:200, project:140 | ✅ |
| ProjectSwitchedEvent | project.switched | project/subscribers.py:107 | codebase:117, project:170 | ✅ |
| NewProjectDetectedEvent | project.new_detected | sync_service:355 | 无 | 📡 |
| IndexingStatusChangedEvent | indexing.status | indexing/manager.py:402 | 无 | 📡 |
| FileModifiedEvent / FileRemovedEvent / FileMovedEvent | indexing.file_* | watchers ×3 | indexing/handlers ×3 | ✅（继承 DynamicBaseModel，**不是** BaseEvent，桥的 isinstance 守卫会丢弃） |
| IndexingEvent | — | **从不实例化** | — | ❌ |
| MemoryContextGatherEvent | memory.context_gather | **publisher 零调用** | project:294, todo:153（永不触发） | ❌ 整条链死 |
| TodoUpdatedEvent | todo.updated | todo/service.py:60 | 无 | 📡 |
| SynthesisCompletedEvent | synthesis.completed | synthesis.py ×2 | 无 | 📡 |
| FileWatcherEvent | fs.*（动态类型） | file/watcher.py ×3 | watcher, skill_file_watcher | ✅ |
| MacroExecutionFailedEvent | macro.execution_failed | macro/service.py:97 | macro/subscribers.py:30 | ✅ |
| VisionProcessStartedEvent / CompletedEvent | vision.process_* | vision/engine.py:35/126 | **零订阅者 + is_public=False** | ❌ |
| AwakenEvent | system.awakening_complete | environment/lifecycle.py:73 | environment:179 | ✅ |
| DeviceConnectedEvent / DisconnectedEvent | device.* | device_watcher ×2 | environment:89/121 | ✅ |
| BoundaryLearnedEvent | system.boundary_learned | environment/boundaries.py:133 | environment:200 | ✅ |
| UiTreeObservedEvent | ui.tree_observed | 发布 ×4 处 | **零订阅者 + is_public=False** | ❌ |

### 2.6 裸 `BaseEvent` 发布（无专属类，靠字符串约定）

| event_type | 发布 | 订阅 |
|---|---|---|
| system.context_polishing | engine/context_hydrator.py:187 | project:245 |
| system.config_changed | config/service.py:81, godcmd:105 | context:22, evocloud:170, mcp:47, project:255 |
| system.embedding_updated | config/embedding.py:102 | codebase:102 |
| learning.skill_created/updated/deleted | skills.py ×6 等 8 处 | learning ×3, routing ×3 |

### 2.7 MessageBlock（**不是事件**）

`MessageBlock`（`app/core/engine/message/schemas.py:87`）继承 `DynamicBaseModel`，**不继承 BaseEvent**。它经 `ChannelRegistry`（WebChannel/MobileChannel）分发，**不经事件总线**。仅在事件系统里作为 `MessageSyncEvent.data` 的载荷类型出现。

---

## 三、订阅者全表（42 个类）

| 模块 | 订阅者类 | 订阅内容 | 总线 |
|---|---|---|---|
| engine/event/subscribers.py | EngineCommandSubscriber | websocket.message_received | system |
| engine/event/subscribers.py | EngineConversationCleanup | conversation.deleted | system |
| project/event/subscribers.py | ProjectSwitchWebSocketSubscriber | websocket.message_received | system |
| project/event/subscribers.py | ProjectDomainSubscriber | project.created/deleted/moved, app_started, user_logged_in, project.switched | system |
| project/event/subscribers.py | ProjectLifecycleSubscriber | app_started/stopping, context_polishing, config_changed | system |
| project/event/subscribers.py | ProjectMemoryContextSubscriber | memory.context_gather ❌永不触发 | system |
| project/event/subscribers.py | ProjectContextHydratorSubscriber | system.session_started | system |
| routing/subscribers.py | VoiceResultSubscriber | system.session_completed, agent.run_completed | system |
| routing/subscribers.py | SkillSedimentationSubscriber | system.session_completed | system |
| routing/subscribers.py | InitSpecRefreshSubscriber | skill_created/updated/deleted | system |
| evocloud/event/subscribers.py | EvoCloudLifecycleSubscriber | app_started/stopping, user_logged_in/out | system |
| evocloud/event/subscribers.py | EvoCloudSyncSubscriber | agent.run_completed | system |
| evocloud/event/subscribers.py | DeviceInfoSyncSubscriber | config_changed | system |
| evocloud/event/subscribers.py | EvoCloudSyncCleanupSubscriber | rewind.messages.cleanup | system |
| learning/event/subscribers.py | LearningLifecycleSubscriber | app_started/stopping, skill_*, session_completed | system |
| learning/event/subscribers.py | TraceRewind | rewind.requested | system |
| learning/event/subscribers.py | LearningConversationCleanup | conversation.deleted | system |
| memory/event/subscribers.py | MemoryLifecycleSubscriber | app_stopping, extraction_requested/completed | system |
| memory/event/subscribers.py | MemoryRewind | rewind.requested | system |
| memory/event/subscribers.py | MemoryConversationCleanup | conversation.deleted | system |
| monitoring/event/subscribers.py | MonitoringLifecycleSubscriber | session_completed | system |
| codebase/event/subscribers.py | IndexingLifecycleSubscriber | app_started/stopping | system |
| codebase/event/subscribers.py | CodebaseSystemEventSubscriber | embedding_updated, project.switched | system |
| codebase/event/subscribers.py | IndexingEventSubscriber | project.created/deleted/moved | system |
| codebase/indexing/handlers.py | DebouncedIndexHandler | indexing.file_modified/removed/moved | system |
| todo/event/subscribers.py | TodoLifecycleSubscriber | extraction_requested/completed | system |
| todo/event/subscribers.py | TodoMemoryContextProvider | memory.context_gather ❌永不触发 | system |
| todo/event/subscribers.py | TodoRewind | rewind.requested | system |
| planning/event/subscribers.py | PlanRewind | rewind.requested | system |
| file/event/subscribers.py | FileRewind | rewind.requested | system |
| context/event/subscribers.py | ContextLifecycleSubscriber | config_changed, conversation.deleted | system |
| mcp/event/subscribers.py | McpLifecycleSubscriber | app_started/stopping, config_changed | system |
| tools/event/subscribers.py | ToolsLifecycleSubscriber | app_started | system |
| atlas/event/subscribers.py | AtlasLifecycleSubscriber | app_started | system |
| execution/macro/event/subscribers.py | MacroSelfHealingAdvisor | macro.execution_failed | system |
| infrastructure/embeddings | EmbeddingLifecycleSubscriber | app_started | system |
| benefits/service.py | BenefitAuthHandler | user_logged_in/out | system |
| environment/event/subscribers.py | EnvironmentLifecycleSubscriber | app_started/stopping | system |
| environment/event/subscribers.py | DeviceEventSubscriber | device.connected/disconnected | **awakening** |
| environment/event/subscribers.py | SkillEventSubscriber | skill.executed/promoted/deprecated ❌永不发布 | **awakening** |
| environment/event/subscribers.py | SystemEventSubscriber | awakening_complete, **state_refreshed ❌跨总线永不触发**, boundary_learned | **awakening** |
| events/subscribers/bridge.py | UniversalBridgeSubscriber | **全部事件**（@event_subscribe_all） | system + awakening |

---

## 四、SSE 层（`app/api/routes/stream.py`）

### `GET /stream/chat/{thread_id}`（24-154）

- **先订阅后 bootstrap**：`cache.pubsub() → chat:{tid}:events`，避免丢事件。
- **Bootstrap**：`activity_monitor.get_activity()` → `event: activity` 快照；若有挂起 HITL，补发 `event: human_request`。
- **循环**：15s `: ping` 心跳；`get_message(timeout=1.0)`；断线指数退避（0.5s→30s，10 次上限）。
- **分发**：`type=="message"` → `MessageNormalizer.normalize_dict(data)` 再序列化；其余类型原样透传 `event: {type}`。

### `GET /stream/system`（157-252）

- 订阅 `system:events`；**不带 `event:` 字段**，只发 `data:` —— 与 chat 端点格式不一致，客户端要两套解析逻辑。

### ⚠️ 发现的问题

1. **热路径有损再归一化**（stream.py:122-125）：`data` 本就是序列化好的 MessageBlock，却再走一遍 `MessageBlockFactory.from_orm`（为 ORM 对象设计）。dict 输入会：
   - 丢 `references`（factory.py:64 用 `hasattr(msg, "references")`，dict 为 False）
   - `sequence_number → 0`、`category → ""`
   - `run_id / parent_id / checkpoint_id / updated_at → None`
   - `is_visible → True`、`is_complete → None`
   - `tool_meta` 每个事件都重新查注册表计算
   
   结果：实时流数据相对发布时**结构降级**（尤其 `sequence_number=0`、`category` 丢失），与历史 API（`/conversations/{id}/messages`，走正确路径）**数据不一致**。

2. **订阅侧绕过抽象**：`stream.py:45` 直调 `cache.pubsub()`，因为 `EventBus` ABC 根本没有 subscribe API。SSE 层耦合到 cache 实现而非总线抽象。

---

## 五、WebChannel（`app/core/channel/web_channel.py`）

| 项 | 内容 |
|---|---|
| name | `"sse"`，accepts_blocks=T，accepts_stream_events=T |
| `send(block)` | `BlockMapper.to_sse` → `MessageSyncEvent.model_dump_json()` → `get_event_bus().publish("chat:{tid}:events")` |
| `send(event)` | `BaseStreamEvent.to_json()` → 同一频道 |
| `send_custom_event` | ✅ 有实现：6 处调用（plan.updated ×5、changeset.updated ×1） |
| `send_hitl_request` | ❌ **继承基类空实现，静默丢弃** —— Web 端 HITL 实际靠 activity.py 发 `HumanRequestEvent` → 桥 |
| `send_envelope` | ❌ 继承基类空实现 |

---

## 六、MobileChannel（`app/core/channel/mobile_channel.py`）

| 项 | 内容 |
|---|---|
| name | `"mobile"`，accepts_blocks=T，accepts_stream_events=F |
| `send(block)` | `BlockMapper.to_mobile`（ISO→unix 时间、丢 thinking/meta_data）→ 封 envelope `message.sync` → HTTP `POST {api}/gateway/api/v1/message/send` |
| 失败回退 | 入队 Huey `mobile_sync_http_task`（retries=2） |
| `send_hitl_request` | ✅ 有实现（HITL_REQUEST envelope） |
| `send_envelope` | ✅ 有实现，3 处调用（command.ack、memory 同步） |
| `send_custom_event` | ❌ 继承基类空实现 —— plan.updated / changesets.updated 移动端永远收不到 |

---

## 七、消息同步：同一份数据上云有 **三条路径**

| 路径 | 目标 | 形态 | 触发 |
|---|---|---|---|
| ① MobileChannel.send | Gateway `/gateway/api/v1/message/send` | 单条、实时、envelope | 每个 MessageBlock |
| ② ConversationSyncManager + Huey | MC `/member/evolooplink/api/sync/{full,conversation,messages}` | 批量、sync_status 跟踪 | 启动全量 + 30min 轮询 + AgentRunCompleted 增量 |
| ③ mobile_sync_http_task（①失败回退） | MC `/member/evolooplink/api/sync/messages` | **单条裸 dict，无 device_key、无 messages 包裹** ⚠️ | ①HTTP 失败 |

一致性靠 MC 幂等 + `sync_status` 标志 + `source=="mobile"` 跳过（dispatch.py:288、sync_tasks.py:236）维持。

**⚠️ 路径 ③ 缺陷**：body 结构与 ②的客户端（`_sync_mixin.py:33-47`，包裹为 `{device_key, thread_id, messages: [...]}`）不一致，且绕过 `EvoCloudHTTPClient`（无 HMAC `X-Signature`、无 token 刷新重试、每次新建 httpx 客户端）——**回退路径大概率被 MC 拒收**，2 次重试只是重复失败。

---

## 八、死代码总清单

### 硬死（零调用，可直接删）

| 类别 | 项目 | 位置 |
|---|---|---|
| 事件类 | RunStartEvent, RunEndEvent, StreamEvent Union | models/schemas/events.py |
| 事件类 | VisionProcessStartedEvent / CompletedEvent（发布但零订阅且不 public） | vision/event/schemas.py |
| 事件类 | UiTreeObservedEvent（发布 ×4 但零订阅且不 public） | environment/event/schemas.py |
| 事件类 | IndexingEvent（从不实例化） | codebase/event/schemas.py |
| 死链 | MemoryContextGatherEvent + publisher + 2 个订阅者 + 类型常量 | memory/event/ |
| 类型 | EventBase（无子类，仅 3 处注解） | pydantic_base.py:17 |
| 总线 API | _lock_pool、mark_initialized、is_initialized、handler_count、clear()（生产）、_initialized | events/base.py |
| 发现 API | auto_discover_all、reset_discovery_cache、get_discovered_stats | events/discovery.py |
| 传输 API | set_event_bus() | engine/message/event_bus.py |
| 发布 API | MessagePublisher.publish_error（仅测试用） | publisher.py:93 |
| 注册 | 5 个 Rewind 的 `register(bus)` classmethod | file/memory/learning/planning/todo |
| 枚举 | AgentEventType 5 个成员（RUN_STARTED/RUN_CANCELLED/TOOL_EXECUTED/HITL_REQUESTED/HITL_RESPONDED） | engine/event/types.py |
| 枚举 | MessageType 7 个成员（command.stop/hitl.response/hitl.cancel/message.deleted/device.status/device.heartbeat/memory.sync） | canonical.py |
| 订阅 | SkillEventSubscriber 的 skill.executed/promoted/deprecated（永不发布） | environment/event/subscribers.py |
| 订阅 | SystemEventSubscriber 的 state_refreshed（跨总线，发布在 system_bus） | environment/event/subscribers.py:191 |
| 消息 | BlockMapper.from_message / to_message / to_db（生产零调用） | mapper.py |
| 消息 | UserMessageMixin.handle_user_message（零调用） | _user_mixin.py:12 |
| 消息 | HITLBlock / HistoryBlock / ToolBlock（schema 无人实例化） | message/schemas.py |
| 包装 | rebuild_event_models()（仅自调用） | events.py:180 |

### 退化实现（活着但实质空转）

- `Channel` 基类 `send_envelope/send_custom_event/send_hitl_request` 默认静默 return → WebChannel 丢 HITL、MobileChannel 丢 custom event。
- `ToolMessageMixin.handle_tool_error` 只改 DB 状态，SSE/移动端都不通知（靠 LLM 后续消息兜底）。

---

## 九、问题总清单（改造依据）

| # | 问题 | 严重度 |
|---|---|---|
| 1 | 三个叫 "event bus" 的东西（system_bus / awakening event_bus / get_event_bus），读代码极易混淆 | 高 |
| 2 | 三个生产者、三种序列化写同一 Redis 频道（WebChannel model_dump_json / 桥 to_frontend_payload+utils_dumps / update_goal 裸 dict 注入 type） | 高 |
| 3 | 传输 ABC 只有 publish 没有 subscribe，stream.py 直调 cache.pubsub() 绕过抽象 | 高 |
| 4 | MessagePublisher 双人格（事件转 bus + 消息块走 channel）+ EventBase 死类型注解 | 高 |
| 5 | **Worker 进程不挂事件系统**（auto_discover_handlers 只在 main.py 调）——tasks.py:560 的 ExtractionCompletedEvent 在 worker 里进空总线，memory/todo 订阅者从不触发 | 高 |
| 6 | SSE 热路径有损再归一化（sequence_number→0、references 丢失），实时流与历史 API 数据不一致 | 高 |
| 7 | 移动回退任务 ③ body 结构与 MC 客户端不一致，绕过签名/鉴权，大概率被拒收 | 中 |
| 8 | AsyncEventBus.publish() 文档谎称 error isolation；并发模式异常照样上抛；_lock_pool 死代码 | 中 |
| 9 | 裸 BaseEvent 发布 ×6（context_polishing/config_changed/embedding_updated/skill_*）、裸字符串事件类型 ×2（subscription.changed/system.log_entry） | 中 |
| 10 | /stream/system 不带 event: 字段，与 chat 端点格式不一致 | 中 |
| 11 | 消息上云三条路径，一致性靠约定维持 | 中 |
| 12 | environment 私有总线只有 3 个订阅者 + 桥手动跨注册 | 低 |

---

## 附：改造方向速览

> 详细方案见后续设计文档。核心思路：

1. **传输层归位**：`EventBus` → `EventTransport`，移入 `app/core/events/transport/`，补齐 subscribe API，stream.py 不再直调 cache。
2. **统一频道命名**：新增 `core/events/channels.py`，消灭 4 处 `chat:{tid}:events` 硬编码。
3. **消灭绕过点**：update_goal、plan.updated、changeset.updated、裸 BaseEvent 发布全部转 typed schema 走 system_bus。
4. **MessagePublisher 职责收窄**：只收 MessageBlock；事件统一 `system_bus.publish()`；移除 EventBase。
5. **Worker 接线**：worker 启动调 `auto_discover_handlers()`。
6. **修复有损归一化**：stream.py 的 message 事件不再走 from_orm。
7. **总线语义修正**：实现真正的 error isolation，删死代码。
