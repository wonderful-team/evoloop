# EvoLoop 测试指南

## 测试思路概述

### 1. 测试分层策略

```
┌─────────────────────────────────────────────────────────┐
│  E2E 测试 (End-to-End)                                   │
│  - 完整用户流程测试                                        │
│  - 需要运行中的后端服务                                     │
│  - 使用 httpx 或 playwright 测试真实 API                  │
├─────────────────────────────────────────────────────────┤
│  集成测试 (Integration)                                   │
│  - 多个组件协作测试                                        │
│  - Mock 外部依赖 (数据库、LLM、Redis)                      │
│  - 测试事件流和数据流                                       │
├─────────────────────────────────────────────────────────┤
│  单元测试 (Unit)                                          │
│  - 单一函数/类测试                                         │
│  - 完全隔离，全部 Mock                                     │
│  - 快速执行，高频运行                                       │
└─────────────────────────────────────────────────────────┘
```

### 2. 测试类型说明

#### A. 单元测试 - 纯逻辑验证

```python
# 测试数据格式
def test_message_format():
    message = {"role": "ai", "content": "Hello"}
    assert "role" in message
    assert message["role"] in ["human", "ai", "tool"]
```

**适用场景：**
- 数据模型验证 (Pydantic Schema)
- 工具函数测试 (utils/)
- 纯算法逻辑 (diff、extract)

#### B. Mock 测试 - 隔离外部依赖

```python
# 使用 unittest.mock 隔离外部依赖
@pytest.mark.asyncio
async def test_chat_node():
    with patch("app.core.engine.AgentEngine") as mock_engine:
        mock_engine.run_node = AsyncMock(return_value={...})
        # 测试逻辑...
```

**适用场景：**
- Agent Node 测试
- 数据库操作测试
- LLM 调用测试

#### C. 参数化测试 - 批量测试

```python
@pytest.mark.parametrize("event_type", [
    "token", "step", "status", "message"
])
def test_event_types(event_type):
    assert event_type in VALID_EVENT_TYPES
```

**适用场景：**
- 多种消息类型验证
- 多种状态验证
- 边界条件测试

#### D. 集成测试 - 组件协作

```python
@pytest.mark.asyncio
async def test_event_flow():
    # 测试回调处理器 → 缓存 → 流式端点的完整流程
    # 使用真实组件，但 Mock 外部服务
```

**适用场景：**
- SSE 事件流测试
- 状态转换测试
- 人机协作流程测试

### 3. 按场景分类的测试建议

#### 聊天对话场景测试

| 场景 | 测试类型 | 关键断言 |
|------|---------|---------|
| 普通对话 | 单元测试 | 消息格式正确 |
| 流式输出 | Mock 测试 | SSE 格式正确 |
| 工具调用 | Mock 测试 | 工具参数正确 |
| 分页加载 | 单元测试 | 分页逻辑正确 |
| HITL 交互 | 集成测试 | 状态流转正确 |

#### 测试文件命名规范

```
tests/
├── unit/                          # 单元测试
│   ├── stream/
│   │   └── test_incremental_updates.py
│   ├── cache/
│   │   └── test_file_cache.py
│   └── context/
│       └── test_tool_state.py
├── test_[模块名].py               # 模块级测试
│   ├── test_conversation_api.py
│   ├── test_chat_node.py
│   └── test_macro_schema_yaml.py
└── utils/                         # 工具函数测试
    └── test_diff.py
```

### 4. 运行测试

```bash
# 运行所有测试
cd backend
python -m pytest tests/ -v

# 运行特定测试文件
python -m pytest tests/test_conversation_api.py -v

# 运行特定测试类
python -m pytest tests/test_chat_node.py::TestChatNode -v

# 运行特定测试方法
python -m pytest tests/test_chat_node.py::TestChatNode::test_chat_node_no_tools -v

# 只运行单元测试（跳过集成测试）
python -m pytest tests/ -v -m "not integration"

# 带覆盖率报告
python -m pytest tests/ --cov=app --cov-report=html
```

### 5. 测试最佳实践

#### DO ✅

- **Mock 外部依赖**：数据库、LLM、Redis、文件系统
- **测试边界条件**：空输入、超大输入、特殊字符
- **使用参数化**：多组数据复用同一测试逻辑
- **测试异常路径**：失败场景、超时、网络错误
- **保持测试独立**：每个测试不依赖其他测试的状态

#### DON'T ❌

- 不要测试第三方库的实现细节
- 不要在单元测试中调用真实的外部 API
- 不要编写执行时间过长的单元测试（> 1秒）
- 不要让测试产生副作用（创建真实文件等）

### 6. 测试示例解析

#### 示例 1：测试消息格式（单元测试）

```python
def test_ai_message_structure():
    """验证 AI 消息包含必需的字段"""
    message = {
        "id": "123",
        "role": "ai",
        "content": "Hello",
        "steps": [],
    }
    
    # 关键断言
    assert "id" in message
    assert message["role"] == "ai"
    assert isinstance(message["content"], str)
```

**测试思路**：验证数据结构符合预期

#### 示例 2：测试 Chat Node（Mock 测试）

```python
@pytest.mark.asyncio
async def test_chat_node_no_tools():
    """验证 Chat Node 不使用工具"""
    with patch("app.core.engine.AgentEngine") as mock:
        mock.run_node = AsyncMock(return_value={...})
        
        # 执行
        result = await chat_node(state, config)
        
        # 验证调用参数
        call_kwargs = mock.run_node.call_args.kwargs
        assert call_kwargs["tools"] == []  # 关键断言
```

**测试思路**：Mock 依赖，验证行为符合预期

#### 示例 3：测试分页（参数化测试）

```python
@pytest.mark.parametrize("limit,expected", [
    (10, 10),
    (50, 50),
    (200, 100),  # 超过最大值
])
def test_pagination_limit(limit, expected):
    validated = min(max(limit, 1), 100)
    assert validated == expected
```

**测试思路**：批量验证边界条件

### 7. 测试覆盖率目标

| 模块 | 目标覆盖率 | 优先级 |
|------|-----------|--------|
| app.core.engine | 80% | P0 |
| app.api.routes | 70% | P0 |
| app.models | 90% | P1 |
| app.utils | 85% | P1 |
| app.domain.tools | 60% | P2 |

### 8. 持续集成建议

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run Tests
        run: |
          pip install pytest pytest-asyncio
          python -m pytest tests/ -v --cov=app
```

---

## 总结

EvoLoop 的测试思路：**分层测试 + Mock 隔离 + 行为验证**

1. **单元测试**验证数据结构和纯逻辑
2. **Mock 测试**验证组件行为（不依赖外部服务）
3. **集成测试**验证组件协作和数据流
4. **参数化测试**高效覆盖多种场景

我前面提供的 `test_conversation_api.py` 和 `test_chat_node.py` 就是按照这个思路编写的真实测试代码，可以直接运行。
