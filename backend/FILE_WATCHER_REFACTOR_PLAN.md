# EvoLoop FileWatcher 重构计划

## 目标
将文件监控能力从 `domain/watchers.py` 下沉到 `core/file/watcher.py`，实现：
1. **标准化文件监控** - core 层提供基础能力
2. **解耦业务逻辑** - domain 层只关注索引/同步
3. **提高可复用性** - 其他模块可直接使用 core.file.watcher

---

## 新架构

```
core/file/watcher.py          # 基础监控能力
├── FileEvent                 # 标准化事件
├── FileEventType             # 事件类型枚举
├── FileWatcher               # 单目录监控
├── FileWatcherManager        # 多目录管理
└── watch()                   # 快捷函数

domain/watchers.py            # 业务层（简化后）
├── IndexingEventHandler      # 使用 core.FileWatcher
├── ProjectDiscoveryWatcher   # 使用 core.FileWatcher
└── GlobalObserverManager     # 可保留或改用 FileWatcherManager
```

---

## 使用示例

### 基础用法

```python
# 直接使用 core 层
from app.core.file.watcher import FileWatcher, FileEvent, FileEventType

async def on_file_change(event: FileEvent):
    if event.type == FileEventType.MODIFIED:
        print(f"File modified: {event.path}")

watcher = FileWatcher("/workspace", on_file_change, debounce_delay=2.0)
watcher.start()
```

### 带过滤的监控

```python
from app.core.file.watcher import FileWatcher

def is_python_file(path: str) -> bool:
    return path.endswith('.py')

watcher = FileWatcher(
    path="/workspace",
    callback=on_change,
    file_filter=is_python_file,
    debounce_delay=1.0
)
```

### 多目录管理

```python
from app.core.file.watcher import FileWatcherManager

manager = FileWatcherManager()

# 监控多个项目
for project_path in projects:
    manager.create_watcher(
        path=project_path,
        callback=on_project_change,
        debounce_delay=2.0
    )

# 统一停止
manager.stop_all()
```

---

## domain/watchers.py 重构方案

### 当前实现（简化）

```python
class IndexingEventHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if self._is_valid_code_file(event.src_path):
            self._debounce_process(event.src_path)
    
    def _debounce_process(self, path: str):
        # 2秒防抖逻辑
        # 调用 IndexingService
```

### 重构后实现

```python
from app.core.file.watcher import FileWatcher, FileEvent, FileEventType

class RepoWatcher:
    """仓库监控器 - 使用 core.FileWatcher"""
    
    def __init__(self, path: str, repo_id: int):
        self.path = path
        self.repo_id = repo_id
        self.service = IndexingService()
        self.watcher: Optional[FileWatcher] = None
    
    def _is_valid_code_file(self, path: str) -> bool:
        # 保留业务过滤逻辑
        return is_code_file(path) and FileFilter().should_include(path)
    
    async def _on_file_change(self, event: FileEvent):
        """文件变更回调"""
        if event.is_directory:
            return
        
        if not self._is_valid_code_file(event.path):
            return
        
        if event.type == FileEventType.MODIFIED:
            logger.info(f"Indexing: {event.path}")
            await self.service.index_file(event.path, self.repo_id)
        
        elif event.type == FileEventType.DELETED:
            await self.service.remove_file(event.path, self.repo_id)
        
        elif event.type == FileEventType.MOVED:
            await self.service.move_file(
                event.path, 
                event.dest_path, 
                self.repo_id
            )
    
    def start(self):
        """启动监控"""
        self.watcher = FileWatcher(
            path=self.path,
            callback=self._on_file_change,
            recursive=True,
            debounce_delay=2.0,
            file_filter=self._is_valid_code_file,
        )
        self.watcher.start()
        logger.info(f"Started watching repo: {self.path}")
    
    def stop(self):
        """停止监控"""
        if self.watcher:
            self.watcher.stop()
```

---

## 收益

### 1. 架构清晰
- **core/file/watcher.py**: 纯技术能力，无业务依赖
- **domain/watchers.py**: 纯业务逻辑，依赖索引服务

### 2. 易于复用
其他模块可以直接使用：
```python
from app.core.file.watcher import FileWatcher

# 配置文件监控
watcher = FileWatcher("/config", on_config_change)

# 日志文件监控
watcher = FileWatcher("/logs", on_log_change, file_filter=is_log_file)
```

### 3. 测试友好
- core 层可独立测试
- domain 层可 mock FileWatcher

### 4. 渐进式迁移
- 新功能使用 core.file.watcher
- 旧代码逐步重构
- GlobalObserverManager 可保留作为兼容层

---

## 迁移步骤

1. **Phase 1**: 部署 `core/file/watcher.py`（已完成）
2. **Phase 2**: 新增业务逻辑使用 core.FileWatcher
3. **Phase 3**: 逐步重构 domain/watchers.py
4. **Phase 4**: 验证后移除旧实现

---

## 是否需要立即执行？

### 建议：**可以但不必立即**

**立即执行的好处：**
- 架构更清晰
- 其他模块可立即使用

**等待的理由：**
- 当前 domain/watchers.py 工作正常
- 重构需要测试验证
- 资源有限时可延后

### 推荐做法
1. **立即**：部署 core/file/watcher.py（已提供）
2. **后续**：新业务使用 core.FileWatcher
3. **择机**：逐步重构 domain/watchers.py

---

**状态**: 重构方案已设计完成，core/file/watcher.py 已可用
