# 事件类型重构完成报告

## 重构概述

将原本集中在 `app/core/events/registry.py` 中的模块特定事件类型，分散到各自的生产者模块中。

## 变更前

所有事件类型集中在 `app/core/events/registry.py`：
- AgentEventType
- MacroEventType  
- RewindEventType
- AwakeningEventType
- ProjectEventType
- ...等

## 变更后

### 模块特定事件类型（分散）

| 事件类型 | 新位置 | 生产者模块 |
|---------|--------|-----------|
| AgentEventType | `app/core/engine/events.py` | app/core/engine/ |
| MacroEventType | `app/core/execution/macro/events.py` | app/core/execution/macro/ |
| RewindEventType | `app/core/rewind/events.py` | app/core/rewind/ |

### 共享事件类型（保留）

保留在 `app/core/events/registry.py`：
- SystemEventType - 系统生命周期
- AwakeningEventType - 环境/设备/技能
- ProjectEventType - 项目生命周期
- IndexingEventType - 代码索引
- FileSystemEventType - 文件系统

## 架构改进

### 高内聚
事件类型定义贴近产生它们的业务代码：
```
app/core/engine/
├── events.py          # AgentEventType 定义
├── agent.py           # Agent 引擎代码
└── ...

app/core/rewind/
├── events.py          # RewindEventType 定义
├── orchestrator.py    # Rewind 协调器
└── ...
```

### 低耦合
`app/core/events/` 只保留基础设施：
- `base.py` - 事件总线
- `decorators.py` - @handles, @auto_register
- `discovery.py` - 自动发现
- `registry.py` - 共享事件类型

### 向后兼容
`app/core/events/__init__.py` 重新导出模块特定事件类型：
```python
from app.core.engine.events import AgentEventType
from app.core.execution.macro.events import MacroEventType
from app.core.rewind.events import RewindEventType
```
现有代码可以继续使用 `from app.core.events import AgentEventType`

## 文件变更清单

### 新增文件
- `app/core/engine/events.py` - Agent 事件类型
- `app/core/execution/macro/events.py` - Macro 事件类型
- `app/core/rewind/events.py` - Rewind 事件类型

### 修改文件
- `app/core/events/registry.py` - 移除模块特定事件类型
- `app/core/events/__init__.py` - 重新导出事件类型
- `app/core/events/decorators.py` - 更新文档示例
- `app/core/learning/orchestrator.py` - 更新导入
- `app/core/learning/self_healing.py` - 更新导入
- `app/core/memory/rewind.py` - 更新导入
- `app/core/file/rewind.py` - 更新导入
- `app/core/rewind/orchestrator.py` - 更新导入
- `app/core/events/rewind.py` - 更新导入
- `app/core/engine/rewind/state.py` - 更新导入
- `app/infrastructure/database/models/rewind.py` - 更新导入
- `app/domain/learning/rewind.py` - 更新导入
- `app/domain/todo/rewind.py` - 更新导入

## 测试状态

```
测试套件: tests/integration/rewind/ + tests/unit/core/rewind/
结果: 27 passed, 0 failed
```

## 架构对比

### 重构前
```
app/core/events/registry.py  (51 种事件类型)
    ↓ 被多个模块导入
app/core/engine/ (使用 AgentEventType)
app/core/rewind/ (使用 RewindEventType)
...
```

### 重构后
```
app/core/engine/events.py    (AgentEventType)
    ↓ 被 app/core/learning/ 消费

app/core/rewind/events.py    (RewindEventType)
    ↓ 被 app/domain/todo/ 等消费

app/core/events/registry.py  (28 种共享事件类型)
    ↓ 被所有模块共享
```

## 优势

1. **高内聚** - 事件类型贴近业务代码
2. **低耦合** - 减少循环导入风险
3. **模块化** - 各模块可以独立演进
4. **清晰依赖** - 显式依赖关系
5. **向后兼容** - 现有代码无需修改
