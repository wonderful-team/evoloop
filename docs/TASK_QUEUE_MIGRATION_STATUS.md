# Task Queue 迁移状态

## 概述

所有业务代码已从直接使用 Celery/LocalCelery 迁移到统一的工厂模式，支持通过 `.env` 配置快速切换后端。

## 迁移状态

### ✅ 已完成迁移的文件（13 个）

| 文件 | 迁移方式 | 说明 |
|------|---------|------|
| `app/domain/wiki/tasks.py` | `shared_task` 装饰器 | Wiki 生成任务 |
| `app/core/engine/tasks.py` | `shared_task` 装饰器 | 引擎后台任务 |
| `app/core/atlas/tasks.py` | `shared_task` 装饰器 | Atlas 任务 |
| `app/domain/codebase/indexing/tasks.py` | `get_scheduler().task()` | 索引任务 |
| `app/domain/project/sync_tasks.py` | `get_scheduler().task()` | 项目同步任务 |
| `app/domain/project/summarizer.py` | `get_scheduler()` | 摘要生成 |
| `app/tasks/memory_tasks.py` | `get_scheduler().task()` | 内存维护任务 |
| `app/core/vision/cleanup.py` | `get_scheduler()` | 清理任务 |
| `app/core/callbacks/database_logger.py` | `get_scheduler()` | 数据库日志 |
| `app/core/engine/__init__.py` | `get_scheduler()` | 引擎初始化 |
| `app/core/engine/tools/learning.py` | `get_scheduler()` | 学习工具 |
| `app/core/evocloud/manager.py` | `get_scheduler()` | EvoCloud 管理 |
| `app/core/vision/engine.py` | `get_scheduler()` | 视觉引擎 |

### ✅ 核心基础设施文件

| 文件 | 说明 |
|------|------|
| `app/infrastructure/queue/factory.py` | 工厂模式入口，统一接口 |
| `app/infrastructure/queue/base.py` | 抽象基类定义 |
| `app/infrastructure/queue/celery.py` | Celery/LocalCelery 实现 |
| `app/infrastructure/queue/huey_queue.py` | Huey (SQLite) 实现 |
| `app/core/config.py` | 新增 `TASK_QUEUE_BACKEND` 配置 |
| `app/main.py` | 集成 Worker 自动启动/停止 |
| `bin/run.py` | 更新为支持多后端的 worker 命令 |

### ⚠️ 遗留文件（向后兼容）

| 文件 | 状态 | 说明 |
|------|------|------|
| `app/infrastructure/queue/celery.py` | 保留但标记 DEPRECATED | 导出 `celery_app` 全局变量供旧代码使用 |

### 📝 测试文件（保持不变）

测试文件仍使用旧导入以测试特定实现细节，不影响生产代码：
- `tests/unit/domain/wiki/test_wiki_agent.py`
- `tests/unit/domain/wiki/test_wiki_agent_core.py`
- `tests/integration/test_wiki_agent_integration.py`

## 使用方式

### 1. 通过装饰器定义任务（推荐）

```python
from app.infrastructure.queue.factory import shared_task

@shared_task(name="my_task", retries=3, retry_delay=60)
def my_task(arg1: str, arg2: int):
    # 任务实现
    pass

# 调用
result = my_task.delay("hello", 42)
```

### 2. 通过 scheduler 动态创建任务

```python
from app.infrastructure.queue.factory import get_scheduler

scheduler = get_scheduler()

@scheduler.task(name="dynamic_task")
def dynamic_task():
    pass
```

### 3. 发送任务（不通过装饰器）

```python
from app.infrastructure.queue.factory import get_scheduler

scheduler = get_scheduler()
result = scheduler.send_task("task_name", args=(1, 2), kwargs={"key": "value"})
```

## 配置切换

### `.env` 文件

```bash
# 选项 1: 嵌入式模式（SQLite + Huey）
EMBEDDED_MODE=true
TASK_QUEUE_BACKEND=auto       # 自动使用 huey

# 选项 2: 生产模式（Redis + Celery）
EMBEDDED_MODE=false
TASK_QUEUE_BACKEND=celery
REDIS_URL=redis://localhost:6379/0

# 选项 3: 嵌入式但强制使用 Celery（需要外部 Redis）
EMBEDDED_MODE=true
TASK_QUEUE_BACKEND=celery
REDIS_URL=redis://localhost:6379/0

# 选项 4: 开发测试（内存模式）
EMBEDDED_MODE=true
TASK_QUEUE_BACKEND=local      # 纯内存，重启丢失
```

## 启动方式

### 方式 1: FastAPI 自动启动（Huey 推荐）

```bash
export EMBEDDED_MODE=true
export TASK_QUEUE_BACKEND=huey
python -m app.main

# 日志输出:
# [QueueFactory] Using configured backend: huey
# [QueueFactory] Created Huey scheduler
# [Startup] ✓ Huey Worker started (backend=huey, 2 threads, daemon mode)
```

### 方式 2: 独立启动 Worker

```bash
# Huey
export TASK_QUEUE_BACKEND=huey
python bin/run.py worker

# Celery
export TASK_QUEUE_BACKEND=celery
python bin/run.py worker
```

### 方式 3: Celery 原生命令（仅 Celery 模式）

```bash
celery -A app.infrastructure.queue.celery worker --loglevel=info
```

## API 兼容性

所有后端提供统一 API：

```python
# 装饰器
@shared_task(name="task_name", retries=3, retry_delay=60)

# 派发任务
result = task.delay(*args, **kwargs)
result = task.apply_async(args=(...), kwargs={...}, countdown=60)

# 获取结果（异步）
value = await result.get(timeout=30)

# 检查状态
if result.ready():
    value = result.get()
```

## 特性对比

| 特性 | Huey (SQLite) | Celery (Redis) | LocalCelery (Memory) |
|------|---------------|----------------|---------------------|
| 持久化 | ✅ 是 | ✅ 是 | ❌ 否 |
| 外部依赖 | ❌ 无 | ✅ Redis | ❌ 无 |
| 分布式 | ❌ 单节点 | ✅ 支持 | ❌ 单节点 |
| 定时任务 | ✅ 支持 | ✅ 支持 | ❌ 不支持 |
| 自动重试 | ✅ 支持 | ✅ 支持 | ❌ 不支持 |
| 适用场景 | 桌面/嵌入式 | 服务器/生产 | 快速测试 |

## 迁移检查清单

- [x] 所有业务代码使用 `factory.shared_task`
- [x] 所有业务代码使用 `factory.get_scheduler`
- [x] `config.py` 添加 `TASK_QUEUE_BACKEND` 配置
- [x] `factory.py` 支持配置读取
- [x] `main.py` 集成 Worker 生命周期管理
- [x] `bin/run.py` 更新多后端支持
- [x] 向后兼容的 `celery_app` 导出
- [x] 完整文档和配置指南

## 注意事项

1. **不要** 在新代码中直接使用 `from app.infrastructure.queue.celery import celery_app`
2. **不要** 在新代码中直接使用 `from celery import shared_task`
3. **始终** 通过 `factory.shared_task` 或 `factory.get_scheduler()` 访问任务队列
4. **测试文件** 可以保持旧导入以测试特定实现

## 问题排查

### 日志标识当前后端

```
[QueueFactory] Using configured backend: huey
[QueueFactory] Created Huey scheduler
```

### 切换无效？

检查配置优先级：
1. 环境变量 `TASK_QUEUE_BACKEND`
2. `.env` 文件
3. 默认值 `"auto"`

清除 Python 缓存：
```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
