# EvoLoop 性能评估与分析

## 1. 概述

本文档汇总 EvoLoop 系统中的性能相关评估、测试和优化点。

---

## 2. 性能测试脚本

### 2.1 可用性能评估工具

| 脚本 | 类型 | 功能描述 | 使用场景 |
|------|------|----------|----------|
| `tests/manual/compare_ocr_providers.py` | 基准测试 | OCR 提供商性能对比（MacOS vs Android） | 评估不同 OCR 方案的延迟和准确性 |
| `tests/manual/marathon_v5.py` | 耐力测试 | 100 步连续操作测试 | 长时间运行稳定性测试 |
| `tests/e2e/test_concurrency.py` | 并发测试 | 多线程/多请求并发测试 | API 并发性能评估 |
| `scripts/test_atlas_e2e.py` | E2E 测试 | Atlas 端到端性能测试 | 移动端自动化性能 |
| `scripts/test_atlas_mobile.py` | 移动测试 | Atlas 移动端专项测试 | 设备控制性能 |

### 2.2 运行性能测试

```bash
# OCR 性能对比
python tests/manual/compare_ocr_providers.py

# 马拉松测试（100 步连续操作）
python tests/manual/marathon_v5.py

# 并发测试
pytest tests/e2e/test_concurrency.py -v

# Atlas 性能测试
python scripts/test_atlas_e2e.py
python scripts/test_atlas_mobile.py
```

---

## 3. 架构性能评估

### 3.1 代理系统架构评估

**文档**: `docs/architecture/agent_system_evaluation.md`

#### 发现的主要瓶颈

| 瓶颈 | 影响 | 建议优化 |
|------|------|----------|
| "Blind Handoff" 开销 | 每次节点切换: 1 次 LLM 调用 + 1 次 DB 写入 | 合并 Coder + Tester 为 DeveloperNode |
| IntentClassifier | 额外的 LLM 调用（分类器 + 路由器） | 使用正则/关键词路由，或合并到 Supervisor |
| Planner 节点 | 简单任务（如"修复文件X"）过度设计 | 转为 Tool 形式，按需调用 |
| Meta-Reviewer | 失败 3 次后外部审查效果有限 | 给 Coder 更好的工具而非外部审查 |

#### 性能指标对比

```
当前架构（Role-Based）:
Supervisor -> Planner -> Coder -> Tester -> Supervisor
= 3 次 LLM 调用 + 3 次 DB 写入

建议架构（Functional）:
Supervisor -> Developer (内部循环) -> Supervisor
= 1 次 LLM 调用（内部自纠正）+ 1 次 DB 写入

预期改进:
- 延迟降低: ~40%
- Token 消耗降低: ~35%
- 成功率提升: 更紧密的反馈循环
```

### 3.2 关键性能指标定义

```python
# 位于 app/core/vision/types.py
@dataclass
class VisionResult:
    task: VisionTask
    success: bool
    elements: list[UIElement]
    latency_ms: float  # <-- 核心性能指标
    metadata: dict
```

---

## 4. 模型性能配置文件

### 4.1 模型性能参数

**文件**: `app/infrastructure/llm/model_profile.py`

支持模型及其性能特征：

| 模型 | 上下文窗口 | 推荐输出 | 视觉支持 | 剪枝阈值 |
|------|-----------|----------|----------|----------|
| gpt-4o | 128K | 4096 | ✅ | 70% |
| gpt-4o-mini | 128K | 4096 | ✅ | 70% |
| claude-3-opus | 200K | 4096 | ✅ | 80% |
| claude-3.5-sonnet | 200K | 8192 | ✅ | 80% |
| deepseek-chat | 64K | 4096 | ❌ | 65% |
| qwen-plus | 128K | 8192 | ❌ | 70% |

### 4.2 自适应上下文管理

```python
class ModelProfile:
    context_window_ratio: float = 0.6      # 60% 用于历史
    prune_threshold_ratio: float = 0.7     # 70% 时触发剪枝
    truncate_limit_tokens: int = 5000     # 单次输出上限

    @property
    def effective_history_tokens(self) -> int:
        return int(self.max_context_tokens * self.context_window_ratio)

    @property
    def prune_threshold_tokens(self) -> int:
        return int(self.effective_history_tokens * self.prune_threshold_ratio)
```

---

## 5. 关键性能测试场景

### 5.1 并发测试 (`tests/e2e/test_concurrency.py`)

```python
# 测试场景 1: 多用户同时聊天
class TestConcurrentChat:
    def test_multiple_simultaneous_chats(self):
        """5 个并发聊天请求"""
        thread_ids = [f"concurrent-thread-{i}" for i in range(5)]

    def test_chat_under_load(self):
        """10 个请求的负载测试"""
        num_requests = 10
        max_acceptable_time = 30  # 秒

# 测试场景 2: 资源限制
class TestResourceLimits:
    def test_large_message_handling(self):
        """1MB 大消息处理"""
        large_message = "x" * (1024 * 1024)

    def test_many_attachments_handling(self):
        """100 个附件处理"""
        many_attachments = [{...} for i in range(100)]

# 测试场景 3: 内存泄漏
class TestMemoryLeaks:
    def test_repeated_operations_memory_stable(self):
        """50 次重复操作内存稳定性"""
        for i in range(50):
            response = client.get("/api/v1/system/health")
```

### 5.2 OCR 性能对比

```python
# tests/manual/compare_ocr_providers.py
async def compare():
    for name, provider in [("MacOSVisionOCRProvider", macos_p),
                           ("AndroidVisionOCRProvider", android_p)]:
        start = time.time()
        res = await provider.process(VisionTask.OCR, screenshot)
        duration = time.time() - start

        # 输出: Count: {len} (Latency: {duration:.2f}s)
```

### 5.3 马拉松测试 (耐力测试)

```python
# tests/manual/marathon_v5.py
class MarathonRunner:
    def __init__(self, total_steps=100):
        self.total_steps = total_steps

    async def run(self):
        start_time = time.time()

        while self.current_step < self.total_steps:
            # 随机应用切换 + 交互
            await self.perform_interaction()

        duration = time.time() - start_time
        logger.info(f"Avg Latency: {duration/self.current_step:.2f}s")
```

---

## 6. 性能优化建议

### 6.1 已实施的优化

| 优化点 | 实现位置 | 效果 |
|--------|----------|------|
| 模型自适应上下文管理 | `model_profile.py` | 根据模型能力自动调整窗口 |
| 对话历史剪枝策略 | `pruning.py` | 防止上下文溢出 |
| 工具输出截断 | `ModelProfile.truncate_limit_tokens` | 限制单次工具输出大小 |
| 并发请求处理 | `test_concurrency.py` | 验证并发稳定性 |

### 6.2 待优化的性能瓶颈

#### 高优先级

1. **节点合并**
   - 当前: Coder -> Tester -> Coder (多次跳转)
   - 建议: DeveloperNode (内部自纠正循环)
   - 收益: 减少 40% 延迟

2. **IntentClassifier 移除**
   - 当前: LLM 分类 + LLM 路由
   - 建议: 正则匹配 + Supervisor 直接路由
   - 收益: 减少 1 次 LLM 调用

3. **数据库连接池**
   - 当前: 每个节点独立连接
   - 建议: 连接池共享
   - 收益: 减少连接开销

#### 中优先级

4. **Vision Pipeline 优化**
   - 当前: 串行处理 OCR -> Detection -> Analysis
   - 建议: 并行处理独立任务
   - 收益: 减少视觉处理延迟

5. **缓存策略**
   - 当前: 有限的项目结构缓存
   - 建议: 智能缓存热点数据
   - 收益: 减少重复 IO

---

## 7. 性能监控指标

### 7.1 建议监控的指标

```python
# 核心指标
LATENCY_METRICS = {
    "llm_call_latency": "单次 LLM 调用延迟",
    "node_transition_latency": "节点切换延迟",
    "vision_processing_latency": "视觉处理延迟",
    "database_query_latency": "数据库查询延迟",
    "end_to_end_task_latency": "端到端任务延迟",
}

THROUGHPUT_METRICS = {
    "requests_per_second": "每秒请求数",
    "tasks_per_minute": "每分钟完成任务数",
    "tokens_per_second": "每秒处理 Token 数",
}

RESOURCE_METRICS = {
    "memory_usage_mb": "内存使用",
    "database_connections": "数据库连接数",
    "redis_memory_usage": "Redis 内存使用",
}
```

### 7.2 性能测试 checklist

```bash
# 1. 单元测试性能
pytest tests/unit/ -v --tb=short

# 2. 集成测试性能
pytest tests/integration/ -v

# 3. 并发测试
pytest tests/e2e/test_concurrency.py -v

# 4. 马拉松测试
python tests/manual/marathon_v5.py

# 5. OCR 基准测试
python tests/manual/compare_ocr_providers.py

# 6. Atlas 性能
python scripts/test_atlas_e2e.py
```

---

## 8. 相关文档

- `docs/architecture/agent_system_evaluation.md` - 代理架构评估
- `app/infrastructure/llm/model_profile.py` - 模型性能配置
- `tests/e2e/test_concurrency.py` - 并发测试
- `tests/manual/marathon_v5.py` - 耐力测试
- `tests/manual/compare_ocr_providers.py` - OCR 基准测试
