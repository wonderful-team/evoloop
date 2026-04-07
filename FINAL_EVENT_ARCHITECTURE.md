# 最终事件架构总结

## 核心原则

`app/core/events/` 只保留**标准化基础设施**，所有事件类型定义在各自的**业务模块**中。

## 目录结构

```
app/core/events/                    # 基础设施（无业务逻辑）
├── __init__.py                     # 导出基础设施和共享事件
├── base.py                         # AsyncEventBus, SystemEventBus
├── registry.py                     # 共享事件类型（28种）
├── decorators.py                   # @handles, @auto_register
├── discovery.py                    # 自动发现机制
├── bridge.py                       # 事件桥接
├── agent.py                        # Agent 事件数据结构
└── rewind.py                       # Rewind 事件数据结构

app/core/engine/
├── events.py                       # AgentEventType
└── ...

app/core/execution/macro/
├── events.py                       # MacroEventType, MacroExecutionFailedEvent
└── ...

app/core/rewind/
├── events.py                       # RewindEventType
└── ...
```

## 事件类型分布

### 共享事件类型（app/core/events/registry.py）
- SystemEventType
- AwakeningEventType
- ProjectEventType
- IndexingEventType
- FileSystemEventType

### 模块特定事件类型
| 事件类型 | 位置 |
|---------|------|
| AgentEventType | app/core/engine/events.py |
| MacroEventType | app/core/execution/macro/events.py |
| RewindEventType | app/core/rewind/events.py |

### 事件数据结构
| 数据结构 | 位置 |
|---------|------|
| AgentRunCompletedEvent | app/core/events/agent.py |
| MacroExecutionFailedEvent | app/core/execution/macro/events.py |
| RewindRequestedEvent, etc. | app/core/events/rewind.py |

## 导入方式

### 基础设施（从 app.core.events）
```python
from app.core.events import system_bus, BaseEvent, AsyncEventBus
from app.core.events import system_bus, BaseEvent, AsyncEventBus
from app.core.events.decorators import handles, auto_register
from app.core.events import AwakeningEventType  # 共享事件类型
```

### 模块特定事件（从各自模块）
```python
from app.core.engine.events import AgentEventType
from app.core.execution.macro.events import MacroEventType, MacroExecutionFailedEvent
from app.core.rewind.events import RewindEventType
```

## 变更清单

### 新增文件
- `app/core/engine/events.py`
- `app/core/execution/macro/events.py`
- `app/core/rewind/events.py`

### 删除文件
- `app/core/events/macro.py`

### 修改文件
- `app/core/events/__init__.py` - 不再导出模块特定事件类型
- `app/core/events/registry.py` - 移除模块特定事件类型
- `app/core/execution/macro/events.py` - 合并 MacroExecutionFailedEvent
- 多个文件更新导入路径

## 测试状态

```
27 passed, 0 failed
```

## 架构优势

1. **无循环导入** - 基础设施不依赖业务模块
2. **高内聚** - 事件类型贴近业务代码
3. **清晰依赖** - 显式导入路径
4. **标准化** - 基础设施独立且稳定
