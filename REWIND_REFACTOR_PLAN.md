# Rewind 架构重构实施计划

## 概览
- **目标**：将紧耦合的回撤逻辑重构为事件驱动的分布式架构
- **工期**：预计 5-7 天
- **风险**：低（渐进式迁移）

---

## 详细阶段规划

### 阶段一：基础设施准备（Day 1）
**目标**：建立事件定义和基础接口

#### 1.1 创建 RewindEventType
```python
# app/core/events/registry.py
# 添加 RewindEventType 枚举

class RewindEventType(str, Enum):
    REWIND_REQUESTED = "rewind.requested"
    REWIND_COMPLETED = "rewind.completed"
    REWIND_FAILED = "rewind.failed"
    MESSAGES_CLEANUP = "rewind.messages.cleanup"
    FILES_CLEANUP = "rewind.files.cleanup"
    MEMORY_CLEANUP = "rewind.memory.cleanup"
    TODO_CLEANUP = "rewind.todo.cleanup"
    STATE_RESET = "rewind.state.reset"
```

#### 1.2 创建 Rewind 事件类
```python
# app/core/events/rewind.py
# 创建 RewindRequestedEvent, RewindCompletedEvent 等
```

**验收标准**：
- [ ] `RewindEventType` 已添加到 registry.py
- [ ] 所有事件类已创建并通过类型检查
- [ ] 单元测试：事件序列化/反序列化

---

### 阶段二：Rewind 模块骨架（Day 1-2）
**目标**：创建核心协调器和注册机制

#### 2.1 创建 rewind 模块目录结构
```
app/core/rewind/
├── __init__.py              # 导出 public API
├── orchestrator.py          # RewindOrchestrator
├── registry.py              # Handler 注册表
├── models.py                # RewindRequest, RewindResult
├── exceptions.py            # RewindError
└── interfaces.py            # RewindHandler 协议/基类
```

#### 2.2 实现 RewindOrchestrator
```python
class RewindOrchestrator:
    def __init__(
        self,
        event_bus: AsyncEventBus,
        graph: CompiledStateGraph,
        checkpointer: BaseCheckpointSaver,
        session_factory: Callable[[], AsyncSession],
    )
    
    async def perform_rewind(self, thread_id: str, **options) -> RewindResult
```

#### 2.3 实现 Handler 注册机制
```python
class RewindRegistry:
    def register_handler(self, event_type: RewindEventType, handler: RewindHandler)
    def get_handlers(self, event_type: RewindEventType) -> list[RewindHandler]
```

**验收标准**：
- [ ] Orchestrator 可实例化
- [ ] Handler 可注册和注销
- [ ] 发布事件时所有订阅 Handler 被调用

---

### 阶段三：迁移 FileRewind Handler（Day 2）
**目标**：迁移文件回撤逻辑

#### 3.1 创建 core/file/rewind.py
```python
class FileRewind:
    """文件回撤处理器"""
    
    @classmethod
    async def register(cls, bus: AsyncEventBus):
        bus.subscribe(RewindEventType.FILES_CLEANUP, cls().handle)
    
    async def handle(self, event: FilesCleanupEvent):
        # 从旧 cleanup.py 迁移逻辑
```

#### 3.2 迁移逻辑
- 从 `app/core/engine/cleanup.py::FileUndoHandler` 迁移
- 保持文件恢复逻辑不变
- 改用事件触发

#### 3.3 双轨运行
- 旧 `cleanup_side_effects()` 仍保留
- 新 Handler 并行运行（仅日志，不实际操作）

**验收标准**：
- [ ] FileRewind Handler 注册成功
- [ ] 回撤时正确识别文件操作
- [ ] 文件恢复逻辑单元测试通过

---

### 阶段四：迁移 MemoryRewind Handler（Day 2-3）
**目标**：迁移记忆回撤逻辑

#### 4.1 创建 core/memory/rewind.py
```python
class MemoryRewind:
    """记忆回撤处理器"""
```

#### 4.2 迁移逻辑
- 从 `cleanup.py::MemoryCleanupHandler` 迁移
- 使用 `memory_manager.delete_memory()`

**验收标准**：
- [ ] MemoryRewind 可正确删除关联记忆
- [ ] 通过 source_message_id 和 run_id 都能查询

---

### 阶段五：迁移 MessageRewind Handler（Day 3）
**目标**：迁移消息回撤逻辑

#### 5.1 创建 infrastructure/database/models/message_rewind.py
```python
class MessageRewind:
    """消息回撤处理器 - 特殊 Handler，还负责查询消息范围"""
    
    async def on_rewind_requested(self, event: RewindRequestedEvent):
        # 查询需要删除的消息范围
        # 发布 MESSAGES_CLEANUP 事件
```

#### 5.2 迁移逻辑
- 从 `history.py::perform_rewind()` 的消息删除部分迁移
- 处理 MessageReference 删除
- 处理 parent_id 更新

**验收标准**：
- [ ] 正确查询消息范围（包含/不包含 target）
- [ ] 正确删除 Message 和 MessageReference
- [ ] 正确重置 parent_id

---

### 阶段六：迁移 TodoRewind Handler（Day 3）
**目标**：迁移待办回撤逻辑

#### 6.1 创建 domain/todo/rewind.py
```python
class TodoRewind:
    """待办事项回撤处理器"""
```

#### 6.2 迁移逻辑
- 从 `cleanup.py::TodoCleanupHandler` 迁移

**验收标准**：
- [ ] 正确删除 thread_id 关联的待办

---

### 阶段七：迁移 StateRewind Handler（Day 4）
**目标**：迁移 LangGraph 状态回撤

#### 7.1 创建 core/engine/rewind/state.py
```python
class StateRewind:
    """LangGraph 状态回撤处理器"""
    
    def __init__(self, graph: CompiledStateGraph):
        self.graph = graph
    
    async def handle(self, event: StateResetEvent):
        # 执行 checkpoint 回滚
```

#### 7.2 迁移逻辑
- 从 `history.py::perform_rewind()` 的 LangGraph 部分迁移
- Checkpoint 发现和匹配逻辑
- State update 逻辑

**验收标准**：
- [ ] 正确发现目标 checkpoint
- [ ] 正确处理 sequence 匹配
- [ ] 正确回滚 state（blackboard, iteration_count）

---

### 阶段八：API 层集成（Day 4-5）
**目标**：更新 API 使用新的 Orchestrator

#### 8.1 更新 conversations.py
```python
# 修改 rewind_conversation 函数
@router.post("/{thread_id}/rewind")
async def rewind_conversation(...):
    orchestrator = request.app.state.rewind_orchestrator
    result = await orchestrator.perform_rewind(thread_id=thread_id, ...)
```

#### 8.2 更新 agent.py
```python
# 修改 retry_chat 函数
# 使用新的 orchestrator.perform_rewind()
```

#### 8.3 更新 lifespan/main.py
```python
async def lifespan(app: FastAPI):
    # ... 现有初始化 ...
    
    # 初始化 RewindOrchestrator
    from app.core.rewind import RewindOrchestrator
    orchestrator = RewindOrchestrator(
        event_bus=system_bus,
        graph=graph,
        checkpointer=checkpointer,
        session_factory=get_db_session,
    )
    app.state.rewind_orchestrator = orchestrator
    
    # 注册所有 Handlers
    from app.core.file.rewind import FileRewind
    from app.core.memory.rewind import MemoryRewind
    from app.infrastructure.database.models.message_rewind import MessageRewind
    from app.domain.todo.rewind import TodoRewind
    from app.core.engine.rewind.state import StateRewind
    
    await FileRewind.register(system_bus)
    await MemoryRewind.register(system_bus)
    await MessageRewind.register(system_bus)
    await TodoRewind.register(system_bus)
    await StateRewind.register(system_bus, orchestrator)
```

**验收标准**：
- [ ] API 调用正常
- [ ] 回撤功能端到端测试通过

---

### 阶段九：移除旧代码（Day 5-6）
**目标**：清理旧的 cleanup.py 和 history.py

#### 9.1 删除旧 CleanupOrchestrator
```python
# app/core/engine/cleanup.py
# 删除 FileUndoHandler, MemoryCleanupHandler, TodoCleanupHandler
# 保留 cleanup_side_effects() 函数，但改为调用 EventBus
# 或完全删除（如果已经双轨验证通过）
```

#### 9.2 简化 history.py
```python
# app/core/engine/history.py
# HistoryService.perform_rewind() 简化为直接调用 orchestrator
# 或完全删除，API 直接调用 orchestrator
```

#### 9.3 更新导入
- 检查所有引用旧 cleanup 的地方
- 更新为新的 EventBus 模式

**验收标准**：
- [ ] 旧代码已删除
- [ ] 无循环导入
- [ ] 所有测试通过

---

### 阶段十：测试与文档（Day 6-7）
**目标**：全面测试和文档

#### 10.1 单元测试
```python
# tests/unit/core/rewind/test_orchestrator.py
# tests/unit/core/file/test_rewind.py
# tests/unit/core/memory/test_rewind.py
# ...
```

#### 10.2 集成测试
```python
# tests/integration/test_rewind.py
# 测试完整回撤流程
```

#### 10.3 E2E 测试
```python
# 测试场景：
# 1. 正常回撤（删除消息、恢复文件）
# 2. Retry 流程
# 3. 部分失败处理
# 4. 无文件操作的回撤
# 5. 多轮对话回撤
```

#### 10.4 文档更新
```markdown
# docs/architecture/rewind.md
# 更新架构文档
# 说明如何使用事件系统扩展回撤功能
```

**验收标准**：
- [ ] 单元测试覆盖率 > 80%
- [ ] 集成测试通过
- [ ] E2E 测试通过
- [ ] 架构文档已更新

---

## 风险与应对

| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|---------|
| LangGraph checkpoint 回滚失败 | 中 | 高 | 保留旧逻辑作为 fallback |
| 事件丢失导致数据不一致 | 低 | 高 | 添加事件持久化和重试机制 |
| Handler 执行顺序依赖 | 中 | 中 | 明确文档说明，必要时添加阶段标识 |
| 性能下降（事件开销） | 低 | 低 | 使用 async gather 并行执行 |

---

## 每日站会检查点

- [ ] 昨日完成内容
- [ ] 今日计划内容
- [ ] 阻塞问题
- [ ] 是否需要调整计划

---

## 完成后检查清单

- [ ] 所有旧代码已删除
- [ ] 新架构文档已更新
- [ ] 团队成员已 review
- [ ] 生产环境监控已配置（回撤失败告警）
