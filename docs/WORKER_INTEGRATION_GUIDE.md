# EvoLoop Worker 集成指南

本文档介绍两种 Worker 集成方式：
1. **FastAPI 内嵌**（已实现，推荐）
2. **Tauri 管理**（备选方案）

---

## 方案 1：FastAPI 内嵌启动（当前实现）

### 实现方式

在 `app/main.py` 的 `lifespan` 中启动 Huey Worker：

```python
# Startup: 启动 Huey Worker
if settings.EMBEDDED_MODE:
    from huey.consumer import Consumer
    _huey_consumer = Consumer(
        huey,
        workers=2,
        worker_type='thread',
        periodic=True,
    )
    threading.Thread(target=_huey_consumer.run, daemon=True).start()

# Shutdown: 停止 Worker
if _huey_consumer:
    _huey_consumer.stop()
```

### 优点

| 优点 | 说明 |
|------|------|
| ✅ 简单 | 无需额外进程管理 |
| ✅ 自动生命周期 | 随 FastAPI 启动/停止 |
| ✅ 单进程 | 适合桌面应用 |
| ✅ 易于调试 | 日志集中 |

### 缺点

| 缺点 | 说明 |
|------|------|
| ⚠️ 共享进程 | Worker 崩溃可能影响 API |
| ⚠️ 资源竞争 | Worker 和 API 共享资源 |
| ⚠️ GIL 限制 | Python 线程不能真正并行 |

### 适用场景

- 桌面应用（Tauri + FastAPI）
- 开发环境
- 轻量级任务处理

---

## 方案 2：Tauri 管理启动（备选）

### 实现方式

Tauri 作为进程管理器，独立启动 Python Worker：

```rust
// src-tauri/src/worker.rs
use std::process::{Command, Child};
use std::sync::Mutex;

pub struct WorkerManager {
    process: Mutex<Option<Child>>,
}

impl WorkerManager {
    pub fn start(&self) -> Result<(), String> {
        let child = Command::new("python")
            .arg("-m")
            .arg("app.scripts.start_worker")
            .arg("--workers=2")
            .spawn()
            .map_err(|e| e.to_string())?;
        
        *self.process.lock().unwrap() = Some(child);
        Ok(())
    }
    
    pub fn stop(&self) {
        if let Some(mut child) = self.process.lock().unwrap().take() {
            let _ = child.kill();
        }
    }
}
```

```typescript
// frontend: 控制 Worker
import { invoke } from '@tauri-apps/api/core';

// 启动 Worker
await invoke('start_worker');

// 停止 Worker
await invoke('stop_worker');

// 重启 Worker
await invoke('restart_worker');
```

### 优点

| 优点 | 说明 |
|------|------|
| ✅ 进程隔离 | Worker 崩溃不影响 API |
| ✅ 独立监控 | Tauri 可以监控 Worker 状态 |
| ✅ 灵活控制 | 可随时启动/停止/重启 |
| ✅ 资源隔离 | 独立进程，不受 GIL 限制 |

### 缺点

| 缺点 | 说明 |
|------|------|
| ⚠️ 复杂 | 需要进程间通信 |
| ⚠️ 状态同步 | 需要管理两个进程 |
| ⚠️ 部署复杂 | 需要分发额外脚本 |

### 适用场景

- 需要高可靠性
- Worker 可能崩溃的场景
- 需要独立监控任务状态

---

## 方案对比

| 维度 | FastAPI 内嵌 | Tauri 管理 |
|------|-------------|-----------|
| **实现复杂度** | 低 | 高 |
| **进程隔离** | 共享进程 | 独立进程 |
| **崩溃影响** | 影响 API | 不影响 API |
| **资源隔离** | 共享 | 独立 |
| **监控能力** | 日志 | 进程监控 |
| **控制能力** | 启动/停止 | 完整控制 |
| **开发调试** | 简单 | 复杂 |
| **部署复杂度** | 低 | 高 |

---

## 推荐配置

### 开发环境
```bash
# 使用 FastAPI 内嵌（默认）
export WORKER_MODE=embedded  # 或省略，默认
```

### 生产环境
```bash
# 使用 Tauri 管理（如需更高可靠性）
export WORKER_MODE=managed
```

---

## 切换方案

### 从 FastAPI 内嵌切换到 Tauri 管理

1. **修改 main.py**：注释掉 Huey 启动代码
2. **添加 Tauri 命令**：实现 worker.rs
3. **前端添加控制 UI**：启动/停止/状态显示
4. **测试进程通信**：确保状态同步

### 从 Tauri 管理切换回 FastAPI 内嵌

1. **修改 main.py**：恢复 Huey 启动代码
2. **移除 Tauri 命令**：删除 worker.rs
3. **简化前端**：移除 Worker 控制 UI

---

## 监控和日志

### FastAPI 内嵌模式

日志统一输出到控制台：
```
[Startup] ✓ Huey Worker started (2 threads, daemon mode)
[Huey] Task wiki_generate started
[Huey] Task wiki_generate completed
```

### Tauri 管理模式

Worker 日志独立文件：
```
~/.evoloop/logs/worker.log
```

前端状态显示：
```typescript
const [workerStatus, setWorkerStatus] = useState('running');
// running | stopped | error
```

---

## 故障排除

### Worker 没有启动

**FastAPI 内嵌模式：**
```bash
# 检查日志
grep "Huey" logs/app.log

# 检查环境变量
echo $EMBEDDED_MODE  # 应为 true
```

**Tauri 管理模式：**
```bash
# 检查进程
ps aux | grep huey_consumer

# 检查日志
cat ~/.evoloop/logs/worker.log
```

### 任务没有执行

1. **检查 Worker 状态**
   ```python
   from app.infrastructure.queue.huey_queue import get_huey_scheduler
   scheduler = get_huey_scheduler()
   huey = scheduler.get_huey()
   print(f"Pending tasks: {huey.pending()}")
   ```

2. **检查数据库权限**
   ```bash
   ls -la ~/.evoloop/task_queue.db
   ```

3. **重启 Worker**
   ```bash
   # FastAPI 内嵌：重启整个应用
   # Tauri 管理：点击重启按钮
   ```

---

## 总结

| 场景 | 推荐方案 |
|------|---------|
| 快速开发/原型 | FastAPI 内嵌 |
| 桌面应用发布 | FastAPI 内嵌（简单可靠） |
| 高可靠性需求 | Tauri 管理 |
| 需要进程监控 | Tauri 管理 |

**当前已实现：FastAPI 内嵌模式**

如需切换到 Tauri 管理模式，参考本指南的"切换方案"部分。
