# 事件机制使用清单 (app/core/ & app/domain/)

## 🔴 核心事件基础设施 (必须)

| 模块 | 文件 | 作用 |
|------|------|------|
| `app.core.events` | `base.py` | AsyncEventBus, SystemEventBus |
| `app.core.events` | `decorators.py` | @handles, @auto_register |
| `app.core.events` | `discovery.py` | 自动发现机制 |
| `app.core.events` | `registry.py` | 事件类型定义 |
| `app.core.events` | `rewind.py` | Rewind 事件定义 |
| `app.core.events` | `agent.py` | Agent 事件定义 |
| `app.core.events` | `macro.py` | Macro 事件定义 |

## 🟢 事件 Handlers (订阅者 - @auto_register)

### app/core/

| 模块 | 文件 | 订阅事件 |
|------|------|---------|
| `core.engine.rewind` | `state.py` | STATE_RESET, REWIND_REQUESTED |
| `core.environment` | `handlers.py` | DEVICE_CONNECTED, DEVICE_DISCONNECTED, SKILL_EXECUTED, SKILL_PROMOTED, SKILL_DEPRECATED, AWAKENING_COMPLETE, STATE_REFRESHED, BOUNDARY_LEARNED |
| `core.file` | `rewind.py` | FILES_CLEANUP, REWIND_REQUESTED |
| `core.learning` | `orchestrator.py` | RUN_COMPLETED |
| `core.learning` | `self_healing.py` | EXECUTION_FAILED |
| `core.memory` | `rewind.py` | MEMORY_CLEANUP, REWIND_REQUESTED |

### app/domain/

| 模块 | 文件 | 订阅事件 |
|------|------|---------|
| `domain.codebase` | `events.py` | system.embedding_updated, project.switched |
| `domain.codebase.indexing` | `event_handlers.py` | PROJECT_CREATED, PROJECT_DELETED, PROJECT_MOVED |
| `domain.learning` | `rewind.py` | TRACE_CLEANUP, REWIND_REQUESTED |
| `domain.todo` | `rewind.py` | TODO_CLEANUP, REWIND_REQUESTED |

## 🟡 事件发布者 (Publisher)

### app/core/

| 模块 | 文件 | 发布事件 |
|------|------|---------|
| `core.atlas` | `tasks.py` | 后台任务事件 |
| `core.callbacks` | `transparent.py`, `database_logger.py` | 回调事件 |
| `core.engine` | `tasks.py`, `background_agent.py`, `state.py` | Agent 执行事件 |
| `core.environment` | `boundaries.py`, `__init__.py`, `device_watcher.py` | 环境事件 |
| `core.evocloud` | `handlers.py` | 云同步事件 |
| `core.execution` | `service.py` | 宏执行事件 |
| `core.file` | `watcher.py` | 文件系统事件 (FILE_MODIFIED 等) |
| `core.monitoring` | `activity.py` | 活动监控事件 |
| `core.rewind` | `orchestrator.py` | RewindRequestedEvent, RewindFailedEvent |
| `core.tools` | `manager.py` | 工具执行事件 |
| `core.vision` | `engine.py` | UI 观察事件 |

### app/domain/

| 模块 | 文件 | 发布事件 |
|------|------|---------|
| `domain.project` | `sync_service.py` | 项目同步事件 |
| `domain.tools` | `find_element.py` | 工具事件 |

## 🔵 事件桥接/转发

| 模块 | 文件 | 作用 |
|------|------|------|
| `core.events` | `bridge.py` | 内部事件 → 前端 (Cache Pub/Sub) |

## 📊 统计

| 类别 | 数量 |
|------|------|
| **核心事件模块** | 7 个文件 |
| **Handlers (订阅者)** | 11 个文件 |
| **Publishers (发布者)** | 16 个文件 |
| **事件桥接** | 1 个文件 |
| **总计使用事件** | 约 35 个文件 |

## 🎯 核心发现

### 使用 @auto_register 的模块 (11 个)
```
app/core/engine/rewind/state.py
app/core/environment/handlers.py
app/core/file/rewind.py
app/core/learning/orchestrator.py
app/core/learning/self_healing.py
app/core/memory/rewind.py
app/core/events/bridge.py
app/domain/codebase/events.py
app/domain/codebase/indexing/event_handlers.py
app/domain/learning/rewind.py
app/domain/todo/rewind.py
```

### 高频发布者
- `core.file.watcher` - 文件系统事件 (11 次引用)
- `core.monitoring.activity` - 活动监控 (12 次发布)
- `core.rewind.orchestrator` - Rewind 协调

### 未来可能的第三方库
如果要用第三方库替换，需要覆盖以上 11 个 handler 和 16 个 publisher。
