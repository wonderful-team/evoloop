# EvoLoop Event System Inventory

## 1. 核心事件基础设施 (app/core/events/)

| 文件 | 功能 | 复杂度 |
|------|------|--------|
| `base.py` | AsyncEventBus, SystemEventBus - 事件总线基础 | 高 |
| `registry.py` | 事件类型枚举 (RewindEventType, ProjectEventType, etc.) | 中 |
| `decorators.py` | @handles, @auto_register - 注解装饰器 | 中 |
| `discovery.py` | 自动发现机制 | 中 |
| `bridge.py` | 事件桥接 (Internal → Cache Pub/Sub) | 中 |
| `agent.py` | AgentRunCompletedEvent 等 | 低 |
| `macro.py` | MacroExecutionFailedEvent 等 | 低 |
| `rewind.py` | RewindRequestedEvent, FilesCleanupEvent 等 | 中 |

## 2. Rewind/Undo 系统 (我们刚重构的)

| Handler | 事件类型 | 状态 |
|---------|---------|------|
| FileRewind | FILES_CLEANUP, REWIND_REQUESTED | ✅ 注解化 |
| MemoryRewind | MEMORY_CLEANUP, REWIND_REQUESTED | ✅ 注解化 |
| MessageRewind | MESSAGES_CLEANUP, REWIND_REQUESTED | ✅ 注解化 |
| TodoRewind | TODO_CLEANUP, REWIND_REQUESTED | ✅ 注解化 |
| TraceRewind | TRACE_CLEANUP, REWIND_REQUESTED | ✅ 注解化 |
| StateRewind | STATE_RESET, REWIND_REQUESTED | ✅ 注解化 |

## 3. Environment/Awakening 系统

| Handler | 事件类型 | 状态 |
|---------|---------|------|
| DeviceEventHandler | DEVICE_CONNECTED, DEVICE_DISCONNECTED | ✅ 注解化 |
| SkillEventHandler | SKILL_EXECUTED, SKILL_PROMOTED, SKILL_DEPRECATED | ✅ 注解化 |
| SystemEventHandler | AWAKENING_COMPLETE, STATE_REFRESHED, BOUNDARY_LEARNED | ✅ 注解化 |

## 4. Learning 系统

| Handler | 事件类型 | 状态 |
|---------|---------|------|
| LearningOrchestrator | RUN_COMPLETED | ✅ 注解化 |
| MacroSelfHealingAdvisor | EXECUTION_FAILED | ✅ 注解化 |

## 5. Codebase/Indexing 系统

| Handler | 事件类型 | 状态 |
|---------|---------|------|
| IndexingEventHandler | PROJECT_CREATED, PROJECT_DELETED, PROJECT_MOVED | ✅ 注解化 |
| CodebaseEventHandler | system.embedding_updated, project.switched | ✅ 注解化 |

## 6. 其他事件使用 (非注解)

| 文件 | 用途 | 类型 |
|------|------|------|
| `file/watcher.py` | 文件监控事件 | 发布 |
| `vision/engine.py` | UI 树观察事件 | 发布 |
| `execution/macro/engine.py` | 宏执行事件 | 发布 |
| `monitoring/activity.py` | 活动监控 | 发布/订阅 |
| `callbacks/*.py` | LangChain 回调 | 回调 |

## 7. 外部事件 (第三方库)

| 来源 | 用途 |
|------|------|
| watchfiles | 文件系统监控 |
| LangChain callbacks | LLM 流式响应 |
| FastAPI lifespan | 应用生命周期 |

## 总结

**当前状态：**
- 核心 handlers: 12 个（全部注解化）
- 事件总线: 2 个（system_bus, event_bus/awaken_bus）
- 事件类型: 约 30+ 种
- 复杂度: 中等偏高

**是否需要第三方库？**

当前系统已经工作，但如果你觉得复杂，可以考虑：
1. **PyDispatcher** - 简单信号/槽机制
2. **blinker** - Flask 风格信号
3. **PyPubSub** - 发布订阅模式

但我觉得当前系统比这些更灵活（支持 async）。

**建议：** 保持当前系统，但简化发现机制。
