# EvoLoop 任务队列迁移指南

## 概述

EvoLoop 已从 LocalCelery（内存存储，易丢失）迁移到 **Huey + SQLite**（持久化存储，无外部依赖）。

同时提供了**工厂模式封装**，可以无缝切换回 Celery（如果需要分布式部署）。

## 架构变化

```
旧架构 (已废弃):
┌─────────────────────────────────────────┐
│  LocalCelery (内存存储)                  │
│  - 任务重启丢失                          │
│  - 无重试机制                           │
│  - 无持久化                             │
└─────────────────────────────────────────┘

新架构 (推荐):
┌─────────────────────────────────────────┐
│  Huey + SQLite                          │
│  - 任务持久化存储                        │
│  - 自动重试                             │
│  - 支持定时任务                          │
│  - 无需 Redis                           │
└─────────────────────────────────────────┘

可选架构 (分布式部署):
┌─────────────────────────────────────────┐
│  Celery + Redis                         │
│  - 分布式 Worker                        │
│  - 高可用                               │
│  - 需要 Redis 服务                       │
└─────────────────────────────────────────┘
```

## 快速开始

### 1. 安装依赖

```bash
cd /path/to/evoloop/backend

# 使用 uv（推荐）
uv pip install -e "."

# 或使用 pip
pip install huey[sqlite]
```

### 2. 验证安装

```bash
python -c "from app.infrastructure.queue.factory import get_scheduler; print('Huey scheduler ready')"
```

## 使用方式

### 定义任务

```python
from app.infrastructure.queue.factory import shared_task

@shared_task(name="my_task", retries=3, retry_delay=60)
def my_task(x: int, y: int) -> int:
    """
    定义一个后台任务。
    
    Args:
        x, y: 输入参数
        
    Returns:
        计算结果
    """
    return x + y
```

### 派发任务

```python
from app.infrastructure.queue.factory import get_scheduler

# 方式1: 使用 task.delay() (推荐)
result = my_task.delay(1, 2)

# 方式2: 使用 scheduler.send_task()
scheduler = get_scheduler()
result = scheduler.send_task("my_task", args=(1, 2))
```

### 获取结果

```python
# 等待结果（带超时）
try:
    value = await result.get(timeout=30)
    print(f"Result: {value}")
except TimeoutError:
    print("Task timed out")

# 检查状态
if result.ready():
    print("Task completed")
if result.successful():
    print("Task succeeded")
```

### 异步任务

```python
@shared_task(name="async_task", retries=3)
async def async_task(data: str) -> str:
    """支持 async/await 的任务"""
    await asyncio.sleep(1)
    return f"Processed: {data}"

# 派发
result = async_task.delay("hello")
value = await result.get(timeout=30)
```

### 定时任务

```python
from app.infrastructure.queue.factory import periodic_task

@periodic_task(cron='0 2 * * *')  # 每天凌晨2点执行
async def daily_cleanup():
    """定时清理任务"""
    pass

@periodic_task(cron='*/30 * * * *')  # 每30分钟执行
async def periodic_sync():
    """定时同步任务"""
    pass
```

## 配置选项

### 环境变量

```bash
# 强制使用 Huey（嵌入式模式）
export EMBEDDED_MODE=true

# 强制使用 Celery（完整模式）
export EMBEDDED_MODE=false
```

### 配置文件

```python
# app/core/config.py

class Settings(BaseSettings):
    # 模式切换
    EMBEDDED_MODE: bool = True  # true=Huey, false=Celery
    
    # Huey 配置
    HUEY_DB_PATH: str = "~/.evoloop/task_queue.db"
    
    # Celery 配置（完整模式）
    REDIS_URL: Optional[str] = None
```

## 启动 Worker

### Huey 模式（嵌入式）

```bash
# 方式1: 使用 huey_consumer 命令行
cd evoloop/backend
huey_consumer.py app.infrastructure.queue.huey_queue.huey \
    --workers=2 \
    --worker-type=thread

# 方式2: 在 Python 中启动
from app.infrastructure.queue.huey_queue import get_huey_scheduler

scheduler = get_huey_scheduler()
scheduler.worker_main(workers=2)
```

### Celery 模式（分布式）

```bash
# 启动 Celery Worker
celery -A app.infrastructure.queue.celery worker --loglevel=info

# 启动 Celery Beat（定时任务）
celery -A app.infrastructure.queue.celery beat --loglevel=info
```

## 切换任务队列后端

### 切换到 Celery（分布式部署）

```python
# app/infrastructure/queue/factory.py

# 强制使用 Celery
scheduler = create_task_scheduler(mode="celery")

# 或使用环境变量
export EMBEDDED_MODE=false
```

### 切换回 Huey（嵌入式）

```python
# 强制使用 Huey
scheduler = create_task_scheduler(mode="huey")

# 或使用环境变量
export EMBEDDED_MODE=true
```

## 任务重试机制

```python
@shared_task(
    name="flaky_task",
    retries=5,           # 最多重试5次
    retry_delay=60       # 每次间隔60秒
)
def flaky_task():
    """可能失败的任务，自动重试"""
    import random
    if random.random() < 0.5:
        raise Exception("Random failure")
    return "Success"
```

## 任务状态查询

```python
# 获取任务结果
result = my_task.delay(1, 2)

# 保存 task_id
 task_id = result.id

# 稍后查询（需要在同一进程或共享存储）
from app.infrastructure.queue.huey_queue import get_huey_scheduler

huey = get_huey_scheduler().get_huey()
result = huey.result(task_id, preserve=True)
```

## 数据库位置

Huey 使用 SQLite 存储任务，默认位置：

```
~/.evoloop/task_queue.db
```

包含的表：
- `huey_task` - 任务队列
- `huey_schedule` - 定时任务
- `huey_result` - 任务结果

## 故障排除

### 任务没有执行

1. **检查 Worker 是否运行**
   ```bash
   ps aux | grep huey_consumer
   ```

2. **检查数据库权限**
   ```bash
   ls -la ~/.evoloop/task_queue.db
   ```

3. **查看日志**
   ```python
   import logging
   logging.getLogger('huey').setLevel(logging.DEBUG)
   ```

### 任务结果丢失

- Huey 默认会清理旧结果（7天）
- 设置 `store_none=False` 保存空结果
- 使用 `preserve=True` 查询结果时保留

### 从 LocalCelery 迁移

```python
# 旧代码 (LocalCelery)
from app.infrastructure.queue.celery import shared_task

@shared_task(name="old_task")
def old_task():
    pass

# 新代码 (Huey)
from app.infrastructure.queue.factory import shared_task

@shared_task(name="old_task", retries=3)  # 添加重试
def old_task():
    pass
```

## 性能对比

| 特性 | LocalCelery | Huey | Celery+Redis |
|------|-------------|------|--------------|
| 持久化 | ❌ 内存 | ✅ SQLite | ✅ Redis |
| 重启恢复 | ❌ 丢失 | ✅ 保留 | ✅ 保留 |
| 自动重试 | ❌ | ✅ | ✅ |
| 定时任务 | ❌ | ✅ | ✅ |
| 分布式 | ❌ | ❌ | ✅ |
| 外部依赖 | 无 | 无 | Redis |
| 启动速度 | 快 | 快 | 较慢 |

## 总结

- **开发/单机部署**: 使用 Huey（默认）
- **分布式/生产部署**: 切换到 Celery
- **API 完全兼容**: 无需修改业务代码

有任何问题请参考：
- [Huey 文档](https://huey.readthedocs.io/)
- [Celery 文档](https://docs.celeryproject.org/)
