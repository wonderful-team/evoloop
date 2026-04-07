# Task Queue 配置指南

## 快速切换

通过环境变量或 `.env` 文件快速切换任务队列后端：

```bash
# .env 文件
TASK_QUEUE_BACKEND=huey      # SQLite 模式（嵌入式默认）
TASK_QUEUE_BACKEND=celery    # Redis 模式（完整模式）
TASK_QUEUE_BACKEND=local     # 内存模式（仅测试）
TASK_QUEUE_BACKEND=auto      # 自动检测（根据 EMBEDDED_MODE）
```

## 配置详解

### `TASK_QUEUE_BACKEND` 选项

| 值 | 后端 | 存储 | 适用场景 | 特点 |
|----|------|------|---------|------|
| `huey` | Huey | SQLite | 桌面/嵌入式 | ✅ 推荐，无需外部依赖，任务持久化 |
| `celery` | Celery | Redis | 服务器/生产 | 分布式，高并发，需要 Redis |
| `local` | LocalCelery | 内存 | 测试/开发 | ⚠️ 不推荐，重启丢失任务 |
| `auto` | 自动 | - | 通用 | EMBEDDED_MODE=true 用 huey，否则 celery |

### 与 `EMBEDDED_MODE` 的关系

```
EMBEDDED_MODE=true  →  自动使用 SQLite + LanceDB + Huey
EMBEDDED_MODE=false →  自动使用 Postgres + Neo4j + Celery(如果TASK_QUEUE_BACKEND=auto)
```

**覆盖规则**：`TASK_QUEUE_BACKEND` 显式设置会覆盖自动检测。

## 配置示例

### 场景 1：桌面应用（推荐）
```bash
# .env
EMBEDDED_MODE=true
TASK_QUEUE_BACKEND=auto    # 自动使用 huey
```

### 场景 2：服务器部署（Celery）
```bash
# .env
EMBEDDED_MODE=false
TASK_QUEUE_BACKEND=celery
REDIS_URL=redis://localhost:6379/0
```

### 场景 3：桌面应用但使用外部 Redis
```bash
# .env
EMBEDDED_MODE=true
TASK_QUEUE_BACKEND=celery    # 强制使用 Celery
REDIS_URL=redis://localhost:6379/0
```

### 场景 4：开发测试
```bash
# .env
EMBEDDED_MODE=true
TASK_QUEUE_BACKEND=local    # 纯内存，快速重启
```

## 启动方式差异

### Huey (SQLite)
```bash
# Worker 随 FastAPI 自动启动
export EMBEDDED_MODE=true
export TASK_QUEUE_BACKEND=huey
python -m app.main

# 或独立启动
python scripts/start_worker.py
```

### Celery (Redis)
```bash
# 需要单独启动 Worker
export TASK_QUEUE_BACKEND=celery
celery -A app.infrastructure.queue.celery worker --loglevel=info

# 再启动 FastAPI
python -m app.main
```

## 验证当前配置

```bash
# 查看启动日志
[QueueFactory] Using configured backend: huey
[QueueFactory] Created Huey scheduler
```

## 迁移注意事项

1. **Huey → Celery**：任务存储在 SQLite，切换到 Celery 后历史任务不可见
2. **Celery → Huey**：需要单独安装 huey: `pip install huey[sqlite]`
3. **local → 其他**：local 模式不持久化，切换无影响

## 代码中检测当前后端

```python
from app.infrastructure.queue.factory import get_scheduler

scheduler = get_scheduler()
print(type(scheduler).__name__)
# HueyTaskScheduler / Celery / LocalCelery
```
