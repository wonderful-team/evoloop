# EvoLoop 文件监控架构文档

## 概述

EvoLoop 现在有两套文件监控方案，满足不同场景需求：

| 方案 | 位置 | 特点 | 适用场景 |
|-----|------|------|---------|
| **watcher_v1** | `core/file/watcher.py` | 独立回调模式 | 简单监控、向后兼容 |
| **watcher_v2** | `core/file/watcher_v2.py` | 事件系统集成 | 复杂系统、解耦需求 |

---

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      Domain Layer                           │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ domain/watchers │  │ 其他业务模块     │                   │
│  │ (codebase索引)  │  │                 │                   │
│  └────────┬────────┘  └────────┬────────┘                   │
│           │                     │                           │
│           │ 订阅                │ 订阅                       │
│           ▼                     ▼                           │
└───────────┬─────────────────────┬───────────────────────────┘
            │                     │
┌───────────▼─────────────────────▼───────────────────────────┐
│                  Core Events System                         │
│              app.core.events.system_bus                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  FileSystemEventType                                │   │
│  │  - FILE_CREATED                                     │   │
│  │  - FILE_MODIFIED                                    │   │
│  │  - FILE_DELETED                                     │   │
│  │  - FILE_MOVED                                       │   │
│  │  - DIRECTORY_CREATED                                │   │
│  │  - DIRECTORY_DELETED                                │   │
│  │  - WATCHER_STARTED                                  │   │
│  │  - WATCHER_STOPPED                                  │   │
│  └─────────────────────────────────────────────────────┘   │
└───────────┬─────────────────────┬───────────────────────────┘
            │                     │
┌───────────▼─────────────────────▼───────────────────────────┐
│                  Core File Watcher                          │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │   watcher_v1    │  │   watcher_v2    │                   │
│  │ (callback模式)  │  │ (event bus模式) │                   │
│  └────────┬────────┘  └────────┬────────┘                   │
│           │                     │                           │
│           ▼                     ▼                           │
│     ┌─────────────────────────────────┐                     │
│     │        watchdog (底层)         │                     │
│     └─────────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 方案对比

### watcher_v1 (独立回调)

```python
from app.core.file import FileWatcherV1, FileEvent

async def on_change(event: FileEvent):
    print(f"File: {event.path}, Type: {event.type}")

watcher = FileWatcherV1("/workspace", on_change, debounce_delay=2.0)
watcher.start()
```

**特点：**
- 简单直接，回调函数接收事件
- 适合单一用途的监控
- 与业务逻辑紧耦合

### watcher_v2 (事件系统集成)

```python
# 1. 启动 watcher（发布事件到总线）
from app.core.file import FileWatcher

watcher = FileWatcher("/workspace", debounce_delay=2.0)
watcher.start()

# 2. 任何模块都可以订阅事件
from app.core.events import system_bus
from app.core.file.events import FileSystemEventType

async def on_file_changed(event):
    print(f"Changed: {event.data['path']}")

system_bus.subscribe(FileSystemEventType.FILE_MODIFIED, on_file_changed)
```

**特点：**
- 解耦，发布-订阅模式
- 多模块可以独立监听
- 与 EvoLoop 事件系统统一

---

## 使用指南

### 场景 1: 简单文件监控

使用 **watcher_v1**：

```python
from app.core.file import FileWatcherV1, FileEventType

async def handler(event):
    if event.type == FileEventType.MODIFIED:
        await process_file(event.path)

watcher = FileWatcherV1("/data", handler, debounce_delay=1.0)
watcher.start()
```

### 场景 2: 多模块协同

使用 **watcher_v2** + 事件系统：

```python
# module_a.py - 启动监控
from app.core.file import FileWatcher

watcher = FileWatcher("/workspace")
watcher.start()

# module_b.py - 索引服务
from app.core.events import system_bus
from app.core.file.events import FileSystemEventType

async def index_file(event):
    await indexing_service.index(event.data['path'])

system_bus.subscribe(FileSystemEventType.FILE_MODIFIED, index_file)

# module_c.py - 日志服务
async def log_change(event):
    logger.info(f"File changed: {event.data['path']}")

system_bus.subscribe(FileSystemEventType.FILE_MODIFIED, log_change)
```

### 场景 3: 替换 domain/watchers.py

新实现：

```python
# domain/watchers.py (重构后)
from app.core.file import FileWatcher
from app.core.events import system_bus
from app.core.file.events import FileSystemEventType

class RepoWatcher:
    def __init__(self, path: str, repo_id: int):
        self.path = path
        self.repo_id = repo_id
        self.watcher = None
        
        # 订阅文件变更事件
        system_bus.subscribe(
            FileSystemEventType.FILE_MODIFIED, 
            self._on_file_modified
        )
    
    def start(self):
        self.watcher = FileWatcher(self.path, debounce_delay=2.0)
        self.watcher.start()
    
    async def _on_file_modified(self, event):
        if event.data['watch_path'] == self.path:
            await indexing_service.index_file(
                event.data['path'], 
                self.repo_id
            )
```

---

## 事件类型

### FileSystemEventType (新)

```python
class FileSystemEventType(str, Enum):
    FILE_CREATED = "fs.file_created"
    FILE_MODIFIED = "fs.file_modified"
    FILE_DELETED = "fs.file_deleted"
    FILE_MOVED = "fs.file_moved"
    DIRECTORY_CREATED = "fs.dir_created"
    DIRECTORY_DELETED = "fs.dir_deleted"
    WATCHER_STARTED = "fs.watcher_started"
    WATCHER_STOPPED = "fs.watcher_stopped"
```

### 事件数据结构

```python
FileWatcherEvent(
    event_type=FileSystemEventType.FILE_MODIFIED,
    timestamp=datetime.now(),
    source="file_watcher",
    data={
        "path": "/workspace/file.py",
        "watch_path": "/workspace",
        # FILE_MOVED 额外字段:
        "dest_path": "/workspace/new_name.py",
        "is_directory": False,
    }
)
```

---

## 迁移建议

### 新功能开发

**推荐：使用 watcher_v2 + 事件系统**

优势：
- 与 EvoLoop 架构一致
- 易于测试和扩展
- 自动支持多订阅者

### 现有代码

**domain/watchers.py**：
- 可以继续使用当前实现
- 新业务逐步使用 watcher_v2
- 择机重构（非紧急）

---

## 完整示例

```python
# example.py
import asyncio
from app.core.file import FileWatcher
from app.core.events import system_bus
from app.core.file.events import FileSystemEventType

# 处理器 1: 索引服务
async def indexing_handler(event):
    if event.event_type == FileSystemEventType.FILE_MODIFIED:
        print(f"[索引] 更新索引: {event.data['path']}")

# 处理器 2: 日志服务
async def logging_handler(event):
    print(f"[日志] 事件: {event.event_type}, 文件: {event.data['path']}")

# 注册处理器
system_bus.subscribe(FileSystemEventType.FILE_MODIFIED, indexing_handler)
system_bus.subscribe(FileSystemEventType.FILE_MODIFIED, logging_handler)
system_bus.subscribe(FileSystemEventType.FILE_CREATED, logging_handler)

# 启动监控
async def main():
    watcher = FileWatcher("/tmp/test", debounce_delay=0.5)
    watcher.start()
    print("监控已启动，修改 /tmp/test 下的文件查看效果")
    
    # 保持运行
    await asyncio.sleep(60)
    
    watcher.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 总结

| 需求 | 推荐方案 |
|-----|---------|
| 简单脚本/工具 | watcher_v1 |
| 复杂系统/多模块 | watcher_v2 + 事件系统 |
| 替换 domain/watchers | watcher_v2 |
| 向后兼容 | watcher_v1 |

**两套方案并存**，根据场景选择最合适的方案。
