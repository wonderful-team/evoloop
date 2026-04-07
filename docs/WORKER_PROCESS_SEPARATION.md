# Worker 进程分离说明

## 变更概述

将 Huey Worker 从 FastAPI lifespan 中拆出，改为**独立进程**运行。

## 原因

### 之前（集成在 lifespan 中）
```python
# app/main.py
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ... 其他初始化 ...
    
    # 在后台线程启动 Worker
    _huey_thread = threading.Thread(target=run_consumer, daemon=True)
    _huey_thread.start()
    
    yield
    
    # 关闭时停止 Worker
    _huey_consumer.stop()
```

**问题：**
- Worker 在后台线程运行，难以监控
- 信号处理复杂（需要禁用 signal handlers）
- Worker 崩溃可能影响主进程
- 无法独立重启 Worker

### 现在（独立进程）
```
Terminal 1: python -m app.main          # 启动 API
Terminal 2: python -m scripts.run_worker # 启动 Worker（独立进程）
```

**优点：**
- 进程隔离，互不影响
- 可以独立重启 Worker
- 信号处理简单
- 更容易监控和日志分离

## 使用方式

### 方式 1：使用 bin/run.py

```bash
# 窗口 1：启动 API
cd evoloop/backend
python bin/run.py api

# 窗口 2：启动 Worker
python bin/run.py worker

# 窗口 2（多 workers）：
python bin/run.py worker --workers=4
```

### 方式 2：直接使用脚本

```bash
# 启动 Worker（默认 2 workers）
python -m scripts.run_worker

# 启动 Worker（4 workers，调试日志）
python -m scripts.run_worker --workers=4 --verbose
```

### 方式 3：开发模式（简化）

```bash
# 使用 Huey 内置命令（如果已安装 huey 命令行）
huey_consumer.py app.infrastructure.queue.huey_queue.huey -w 2
```

## 进程管理建议

### 使用 systemd（Linux 生产环境）

```ini
# /etc/systemd/system/evoloop-api.service
[Unit]
Description=EvoLoop API
After=network.target

[Service]
Type=simple
User=evoloop
WorkingDirectory=/opt/evoloop/backend
ExecStart=/opt/evoloop/venv/bin/python -m app.main
Restart=always

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/evoloop-worker.service
[Unit]
Description=EvoLoop Worker
After=network.target

[Service]
Type=simple
User=evoloop
WorkingDirectory=/opt/evoloop/backend
ExecStart=/opt/evoloop/venv/bin/python -m scripts.run_worker --workers=2
Restart=always

[Install]
WantedBy=multi-user.target
```

启动：
```bash
sudo systemctl start evoloop-api
sudo systemctl start evoloop-worker
```

### 使用 supervisord（推荐）

```ini
# /etc/supervisor/conf.d/evoloop.conf
[program:evoloop-api]
command=python -m app.main
directory=/opt/evoloop/backend
autostart=true
autorestart=true

[program:evoloop-worker]
command=python -m scripts.run_worker --workers=2
directory=/opt/evoloop/backend
autostart=true
autorestart=true
```

### 使用 Docker

```dockerfile
# Dockerfile.worker
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "-m", "scripts.run_worker", "--workers=2"]
```

```yaml
# docker-compose.yml
version: '3'
services:
  api:
    build: .
    command: python -m app.main
    ports:
      - "8000:8000"
  
  worker:
    build: .
    command: python -m scripts.run_worker --workers=2
```

## 文件变更

| 文件 | 变更 |
|------|------|
| `app/main.py` | 移除 lifespan 中的 Worker 启动/停止代码 |
| `scripts/run_worker.py` | 新建：独立 Worker 启动脚本 |
| `bin/run.py` | 更新 worker 命令，调用独立脚本 |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `TASK_QUEUE_BACKEND` | 队列后端 | `auto` |
| `EMBEDDED_MODE` | 嵌入式模式 | `false` |

## 日志

Worker 日志输出到 stdout/stderr，可以重定向到文件：

```bash
python -m scripts.run_worker --verbose 2>&1 | tee worker.log
```

或使用 systemd journal：
```bash
sudo journalctl -u evoloop-worker -f
```

## 监控

Worker 支持健康检查（每 10 秒），可以通过日志监控：
```
[Worker] Health check: OK (workers=2, tasks_processed=...)
```

## 故障排查

### Worker 无法启动
```bash
# 检查配置
python -c "from app.core.config import settings; print(f'Backend: {settings.TASK_QUEUE_BACKEND}')"

# 手动启动查看详细错误
python -m scripts.run_worker --verbose
```

### Worker 崩溃重启
如果使用 systemd/supervisord，会自动重启。

手动重启：
```bash
# 查找 worker 进程
ps aux | grep run_worker

# 杀死并重启
kill <pid>
python -m scripts.run_worker
```

## 回滚

如需恢复集成模式，撤销 `app/main.py` 的修改即可。
