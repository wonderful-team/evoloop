# Wiki Agent 测试指南

## 测试环境说明

本项目使用**嵌入式模式 (Embedded Mode)**，不需要外部服务：

- ✅ **无需 Redis** - 使用 `LocalCelery` 进行进程内任务调度
- ✅ **无需 Celery Worker** - 任务在同一个进程的事件循环中执行
- ✅ **无需 RabbitMQ** - 没有消息队列依赖

## 测试文件结构

```
tests/
├── unit/domain/wiki/
│   ├── __init__.py
│   └── test_wiki_agent.py          # 单元测试
├── integration/
│   └── test_wiki_agent_integration.py  # 集成测试
└── README_WIKI_AGENT.md            # 本文件
```

## 运行测试

### 运行单元测试

```bash
cd evoloop/backend
pytest tests/unit/domain/wiki/test_wiki_agent.py -v
```

### 运行集成测试

```bash
cd evoloop/backend
pytest tests/integration/test_wiki_agent_integration.py -v
```

### 运行所有 Wiki 相关测试

```bash
cd evoloop/backend
pytest tests/ -k "wiki" -v
```

## 嵌入式模式 (LocalCelery) 特点

### 任务执行方式

```python
from app.domain.wiki.tasks import generate_wiki_task
from app.infrastructure.queue.celery import LocalTask, LocalAsyncResult

# 验证是 LocalTask
assert isinstance(generate_wiki_task, LocalTask)

# 方式1: 使用 delay() - 异步执行，返回 LocalAsyncResult
result = generate_wiki_task.delay(project_id=1, topic="Test")
assert isinstance(result, LocalAsyncResult)

# 等待结果
async def wait_result():
    value = await result.get(timeout=30)
    print(value)

# 方式2: 直接调用 - 同步执行（创建新事件循环）
# 注意：在已有事件循环中（如 pytest-asyncio）直接调用会失败
generate_wiki_task(project_id=1, topic="Test")
```

### 与 Full Mode (Celery + Redis) 的区别

| 特性 | Embedded Mode | Full Mode |
|------|--------------|-----------|
| 依赖 | 无外部依赖 | Redis, Celery Worker |
| 任务执行 | 进程内 asyncio | 独立 worker 进程 |
| 持久化 | 内存（重启丢失） | Redis 后端 |
| 适用场景 | 开发、测试、桌面应用 | 生产环境、分布式 |
| 配置 | `EMBEDDED_MODE=true` | `EMBEDDED_MODE=false` |

## 编写测试的最佳实践

### 1. 使用 AsyncMock 模拟异步依赖

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_structure_worker():
    with patch("app.domain.wiki.nodes.structure_worker.get_default_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value.ainvoke = AsyncMock(return_value=mock_response)
        # ... 测试代码
```

### 2. 模拟 EvoCloud 调用

```python
with patch("app.domain.wiki.nodes.structure_worker.evocloud_manager.get_project_by_id", new_callable=AsyncMock) as mock_cloud:
    mock_cloud.return_value = {"path": "/tmp/test_project"}
    # ... 测试代码
```

### 3. 测试任务执行

```python
@pytest.mark.asyncio
async def test_wiki_task():
    from app.domain.wiki.tasks import generate_wiki_task
    
    with patch("app.domain.wiki.tasks.wiki_service.generate_wiki", new_callable=AsyncMock) as mock_service:
        # 使用 delay() 启动异步任务
        result = generate_wiki_task.delay(project_id=1, topic="Test")
        
        # 等待完成
        value = await result.get(timeout=10)
        assert "Wiki generated" in value
```

### 4. 验证状态转换

```python
@pytest.mark.asyncio
async def test_workflow_state_transitions():
    engine = WikiAgentEngine()
    engine._initialized = True
    engine.graph = MagicMock()
    
    # 捕获状态变化
    states = []
    async def mock_ainvoke(state, config):
        states.append(dict(state))
        return {"completed_pages": 3, "generated_pages": []}
    
    engine.graph.ainvoke = mock_ainvoke
    
    result = await engine.generate_wiki(project_id=1, topic="Test")
    
    # 验证状态流转
    assert len(states) > 0
    assert states[0]["current_page_index"] == 0
```

## 常见问题

### Q: 测试超时怎么办？

```python
# 使用更长的超时时间
result = await result.get(timeout=60)  # 默认可能是 30 秒
```

### Q: 如何在测试中验证 LocalCelery？

```python
from app.infrastructure.queue.celery import LocalCelery, celery_app

# 确认是嵌入式模式
assert settings.EMBEDDED_MODE is True
assert isinstance(celery_app, LocalCelery)

# 确认任务已注册
assert "wiki_generate" in celery_app.tasks
```

### Q: 如何模拟 Graph 执行？

```python
engine.graph = MagicMock()
engine.graph.ainvoke = AsyncMock(return_value={
    "completed_pages": 3,
    "generated_pages": [...],
})
```

## 调试技巧

### 启用详细日志

```python
import logging
logging.getLogger("app.domain.wiki").setLevel(logging.DEBUG)
```

### 检查任务注册

```python
from app.infrastructure.queue.celery import celery_app

print("Registered tasks:")
for name in celery_app.tasks.keys():
    print(f"  - {name}")
```

### 验证 YAML 配置

```python
import yaml
from app.core.engine.schema import AgentConfig

with open("app/config/agents/wiki_agent.yml") as f:
    config = yaml.safe_load(f)
    
# 验证配置
agent_config = AgentConfig(**config)
print(f"Nodes: {[n.id for n in agent_config.nodes]}")
print(f"Edges: {len(agent_config.edges)}")
```

## CI/CD 注意事项

在 CI 环境中，测试会自动使用 Embedded Mode：

```yaml
# .github/workflows/test.yml 示例
- name: Run Wiki Agent Tests
  run: |
    cd evoloop/backend
    pytest tests/unit/domain/wiki/ tests/integration/test_wiki_agent_integration.py -v
  env:
    EVOLOOP_EMBEDDED_MODE: "true"
```

无需设置 Redis 或其他外部服务！
