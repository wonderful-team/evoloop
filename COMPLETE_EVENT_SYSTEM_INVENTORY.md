# EvoLoop 完整事件系统清单

## 一、事件类型定义 (51 种)

### 文件: `app/core/events/registry.py`

| 枚举类 | 数量 | 事件名称 |
|--------|------|----------|
| **SystemEventType** | 2 | APP_STARTED, APP_STOPPING, UNHANDLED_ERROR |
| **AwakeningEventType** | 12 | DEVICE_CONNECTED, DEVICE_DISCONNECTED, NETWORK_ONLINE, NETWORK_OFFLINE, CONCEPT_LEARNED, EPISODE_COMPLETED, SKILL_EXECUTED, SKILL_PROMOTED, SKILL_DEPRECATED, APP_LAUNCHED, APP_PROBED, UI_TREE_OBSERVED, AWAKENING_COMPLETE, STATE_REFRESHED, BOUNDARY_LEARNED |
| **ProjectEventType** | 6 | PROJECT_CREATED, PROJECT_DELETED, PROJECT_MOVED, PROJECT_SYNCED, PROJECT_SWITCHED, NEW_PROJECT_DETECTED |
| **IndexingEventType** | 5 | INDEXING_STARTED, INDEXING_COMPLETED, INDEXING_FAILED, FILE_INDEXED, FILE_REMOVED |
| **FileSystemEventType** | 8 | FILE_CREATED, FILE_MODIFIED, FILE_DELETED, FILE_MOVED, DIRECTORY_CREATED, DIRECTORY_DELETED, WATCHER_STARTED, WATCHER_STOPPED |
| **AgentEventType** | 6 | RUN_STARTED, RUN_COMPLETED, RUN_CANCELLED, TOOL_EXECUTED, HITL_REQUESTED, HITL_RESPONDED |
| **MacroEventType** | 1 | EXECUTION_FAILED |
| **RewindEventType** | 11 | REWIND_REQUESTED, REWIND_COMPLETED, REWIND_FAILED, MESSAGES_CLEANUP, FILES_CLEANUP, MEMORY_CLEANUP, TODO_CLEANUP, TRACE_CLEANUP, CHECKPOINT_CLEANUP, STATE_RESET, BLACKBOARD_RESET |

---

## 二、核心基础设施文件 (7 个)

| 文件 | 功能 | 代码行数 |
|------|------|----------|
| `app/core/events/__init__.py` | 导出公共 API | ~50 |
| `app/core/events/base.py` | AsyncEventBus, SystemEventBus | ~181 |
| `app/core/events/registry.py` | 事件类型枚举定义 | ~146 |
| `app/core/events/agent.py` | AgentRunCompletedEvent 等 | ~30 |
| `app/core/events/macro.py` | MacroExecutionFailedEvent | ~20 |
| `app/core/events/rewind.py` | Rewind 相关事件类 | ~100 |
| `app/core/events/decorators.py` | @handles, @auto_register | ~150 |
| `app/core/events/discovery.py` | 自动发现机制 | ~250 |
| `app/core/events/bridge.py` | 事件桥接 (→前端) | ~90 |

**小计: 9 个文件, 约 1000 行代码**

---

## 三、事件 Handlers (订阅者 - 11 个文件)

### app/core/ (7 个)

| 文件 | Handler 类 | 订阅事件数 |
|------|-----------|-----------|
| `app/core/engine/rewind/state.py` | StateRewind | 2 |
| `app/core/environment/handlers.py` | DeviceEventHandler, SkillEventHandler, SystemEventHandler | 8 |
| `app/core/file/rewind.py` | FileRewind | 2 |
| `app/core/learning/orchestrator.py` | LearningOrchestrator | 1 |
| `app/core/learning/self_healing.py` | MacroSelfHealingAdvisor | 1 |
| `app/core/memory/rewind.py` | MemoryRewind | 2 |
| `app/core/events/bridge.py` | EventBridgeHandler | 1 (subscribe_all) |

### app/domain/ (4 个)

| 文件 | Handler 类 | 订阅事件数 |
|------|-----------|-----------|
| `app/domain/codebase/events.py` | CodebaseEventHandler | 2 |
| `app/domain/codebase/indexing/event_handlers.py` | IndexingEventHandler | 3 |
| `app/domain/learning/rewind.py` | TraceRewind | 2 |
| `app/domain/todo/rewind.py` | TodoRewind | 2 |

**小计: 11 个文件, 12 个 Handler 类**

---

## 四、事件发布者 (主要文件 16 个)

### app/core/ (12 个)

| 文件 | 发布场景 |
|------|----------|
| `app/core/rewind/orchestrator.py` | Rewind 操作触发 |
| `app/core/file/watcher.py` | 文件系统变更 |
| `app/core/environment/__init__.py` | Agent 唤醒完成 |
| `app/core/environment/boundaries.py` | 边界学习 |
| `app/core/environment/device_watcher.py` | 设备连接/断开 |
| `app/core/monitoring/activity.py` | 活动追踪 |
| `app/core/callbacks/transparent.py` | LangChain 回调 |
| `app/core/engine/tasks.py` | 引擎任务 |
| `app/core/engine/background_agent.py` | Agent 运行 |
| `app/core/execution/service.py` | 宏执行 |
| `app/core/evocloud/handlers.py` | 云同步 |
| `app/core/vision/engine.py` | UI 观察 |

### app/domain/ (4 个)

| 文件 | 发布场景 |
|------|----------|
| `app/domain/project/sync_service.py` | 项目同步 |
| `app/domain/tools/find_element.py` | 工具执行 |

---

## 五、环境事件定义 (2 个文件)

| 文件 | 功能 |
|------|------|
| `app/core/environment/events.py` | AwakenEvent, EventType, event_bus |
| `app/core/vision/events.py` | Vision 相关事件 |

---

## 六、项目事件定义 (1 个文件)

| 文件 | 功能 |
|------|------|
| `app/domain/project/events.py` | ProjectCreatedEvent, ProjectDeletedEvent 等 |

---

## 七、模型事件定义 (1 个文件)

| 文件 | 功能 |
|------|------|
| `app/models/schemas/events.py` | 事件相关的 Pydantic 模型 |

---

## 八、API 层使用事件 (4 个文件)

| 文件 | 使用方式 |
|------|----------|
| `app/api/routes/agent.py` | 调用 RewindOrchestrator |
| `app/api/routes/conversations.py` | 调用 RewindOrchestrator |
| `app/api/routes/stream.py` | 活动监控 |
| `app/api/routes/learning.py` | 学习相关 |

---

## 九、Main.py 集成 (1 个文件)

| 文件 | 功能 |
|------|------|
| `app/main.py` | auto_discover_handlers(), register_event_bridge() |

---

## 十、总结

### 文件统计

| 类别 | 文件数 | 说明 |
|------|--------|------|
| 核心基础设施 | 9 | 事件总线、类型、装饰器、发现、桥接 |
| Handlers (订阅者) | 11 | 12 个 Handler 类 |
| Publishers (发布者) | 16 | 发布事件的业务代码 |
| 环境/项目事件定义 | 3 | 领域特定事件 |
| 模型定义 | 1 | Pydantic 模型 |
| API 层 | 4 | REST API 调用 |
| 主程序 | 1 | 启动集成 |
| **总计** | **45 个文件** | 约占后端代码 15% |

### 事件统计

| 类别 | 数量 |
|------|------|
| 事件类型定义 | 51 种 |
| Handler 类 | 12 个 |
| 使用 @auto_register | 11 个类 |
| 使用 @handles | 约 25 个方法 |

### 依赖关系

```
API Layer (agent.py, conversations.py)
    ↓ 调用
RewindOrchestrator / Other Services
    ↓ 发布事件
AsyncEventBus / SystemEventBus
    ↓ 分发
Handlers (FileRewind, MemoryRewind, etc.)
    ↓ 处理
Business Logic
```

### 是否可以简化？

**当前状态**: 45 个文件涉及事件系统
**如果移除此系统**: 
- 需要 12 个 Handler 直接调用服务
- 需要 16 个 Publisher 直接调用 Handler
- 失去解耦和扩展性

**建议**: 保持当前系统，它提供了良好的解耦。
