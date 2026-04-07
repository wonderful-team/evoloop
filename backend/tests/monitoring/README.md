# EvoLoop 对话测试监控系统

## 系统概述

这是一个**真实 LLM 测试执行与监控系统**，用于：
- ✅ 使用真实话术测试 Agent + LLM
- ✅ 实时监控异常（超时、重复、幻觉等）
- ✅ 发现问题时自动切断
- ✅ 记录详细过程与根因
- ✅ 支持修正后重新测试

---

## 📁 文件结构

```
tests/monitoring/
├── test_executor.py          # 核心测试执行器（带监控）
├── batch_runner.py           # 批量测试运行器
├── anomaly_analyzer.py       # 异常分析与根因定位
├── reports/                  # 测试报告目录
│   ├── {session_id}.json     # 单个测试报告
│   └── batch_summary_*.json  # 批量测试汇总
├── logs/                     # 运行日志
└── README.md                 # 本文档
```

---

## 🚀 快速开始

### 1. 环境准备

```bash
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend

# 安装依赖
pip install httpx pytest pytest-asyncio

# 确保后端服务运行
python -m app.main  # 在另一个终端
```

### 2. 单场景测试（带实时监控）

```bash
# 测试代码生成场景（实时监控，异常时切断）
python tests/monitoring/test_executor.py --scenario code_generation --max-rounds 5

# 自动模式（不询问确认）
python tests/monitoring/test_executor.py --scenario debugging --max-rounds 3 --auto
```

**运行中交互：**
```
[第 1 轮] 用户: 帮我写一个 Python 函数，计算斐波那契数列...
   AI (2.3s, 245tokens): 好的，我来为你写一个斐波那契函数...
   工具调用: write_file

[第 2 轮] 用户: 改成递归写法...
   AI (1.8s, 180tokens): 这是递归版本的实现...

⚠️  检测到异常 [repetition]: 与第 1 轮重复度 95%
🛑 关键异常，切断测试！

选项: [c]继续 [r]重试当前轮 [s]跳过 [q]退出
选择: r
重试当前轮...
```

### 3. 批量测试

```bash
# 运行所有场景
python tests/monitoring/batch_runner.py --all --max-rounds 3

# 运行特定场景，失败自动重试
python tests/monitoring/batch_runner.py \
    --scenarios code_generation,debugging,knowledge_query \
    --max-rounds 3 \
    --retry \
    --max-retries 2
```

### 4. 异常分析与修正

```bash
# 查看最近测试的异常详情和修复建议
python tests/monitoring/anomaly_analyzer.py --latest

# 交互式修正后重试
python tests/monitoring/batch_runner.py --interactive

# 分析异常趋势（最近7天）
python tests/monitoring/anomaly_analyzer.py --trend --days 7
```

---

## 📊 异常类型说明

| 异常类型 | 触发条件 | 自动切断 | 常见原因 |
|---------|---------|---------|---------|
| `timeout` | 响应 > 30s | ❌ | 网络慢、模型负载高 |
| `error_response` | 返回错误信息 | ✅ | API 错误、配置问题 |
| `empty_response` | 内容 < 10 字符 | ❌ | Prompt 问题、过滤 |
| `repetition` | 与历史相似度 > 90% | ❌ | temperature 过低 |
| `infinite_loop` | ReAct 循环未终止 | ✅ | 逻辑错误、缺失终止条件 |
| `hallucination` | 检测到编造内容 | ❌ | 模型幻觉 |
| `tool_failure` | 工具调用失败 | ✅ | 参数错误、权限问题 |
| `context_loss` | 上下文丢失 | ❌ | 窗口截断、合并错误 |
| `cost_anomaly` | Token > 4000 | ❌ | 输出过长、循环 |

---

## 🔄 测试-发现-修正-重试 流程

```
┌─────────────────────────────────────────────────────────────┐
│  1. 执行测试                                                │
│     python test_executor.py --scenario code_generation      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  2. 实时监控                                                │
│     - 观察每轮响应                                          │
│     - 检测异常（超时、重复、错误等）                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
         ▼                           ▼
┌─────────────────┐       ┌─────────────────┐
│  3a. 发现异常    │       │  3b. 正常完成    │
│  自动切断测试    │       │  生成报告       │
└────────┬────────┘       └─────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  4. 分析根因                                                │
│     python anomaly_analyzer.py --latest                     │
│     - 查看异常详情                                          │
│     - 获取修复建议                                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  5. 修正问题                                                │
│     - 修改代码/配置                                         │
│     - 调整 Prompt                                           │
│     - 修复工具逻辑                                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  6. 重新测试                                                │
│     python batch_runner.py --interactive                    │
│     或重运行单场景测试                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 报告解读

### 单测试报告 (`{session_id}.json`)

```json
{
  "session_id": "code_generation_20240322_143052",
  "scenario_name": "code_generation",
  "status": "interrupted",
  "rounds": [
    {
      "round": 1,
      "user_input": "帮我写一个 Python 函数...",
      "response": "好的，这是一个斐波那契函数...",
      "response_time_ms": 2340,
      "tokens": 245,
      "tools": ["write_file"],
      "anomaly": "none"
    },
    {
      "round": 2,
      "user_input": "改成递归写法",
      "response": "好的，这是一个斐波那契函数...",
      "anomaly": "repetition",
      "anomaly_detail": "与第 1 轮重复度 95%"
    }
  ],
  "anomalies": [
    {
      "round": 2,
      "type": "repetition",
      "detail": "与第 1 轮重复度 95%",
      "timestamp": 1711091452
    }
  ],
  "interrupted_at": 2,
  "interrupt_reason": "检测到异常: repetition",
  "total_tokens": 890,
  "total_cost": 0.0001335
}
```

### 批量测试汇总 (`batch_summary_*.json`)

```json
{
  "timestamp": "2024-03-22T14:30:00",
  "total_scenarios": 10,
  "success": 7,
  "failed": 3,
  "success_rate": 0.7,
  "total_cost_usd": 0.015,
  "anomaly_breakdown": {
    "timeout": 2,
    "repetition": 3,
    "tool_failure": 1
  }
}
```

---

## 🎛️ 高级配置

### 修改监控阈值

编辑 `test_executor.py`:

```python
class AnomalyDetector:
    def __init__(self):
        self.max_similarity_threshold = 0.9  # 重复检测阈值
        # ...
    
    def check(self, record):
        # 响应时间阈值
        if record.response_time_ms > 30000:  # 30秒
            return AnomalyType.TIMEOUT, "响应时间过长"
        
        # Token 阈值
        if record.tokens_used > 4000:
            return AnomalyType.COST_ANOMALY, "Token 使用量异常"
```

### 添加自定义异常检测

```python
def check_custom_anomaly(self, record):
    # 检测特定模式
    if "我不明白" in record.response_content:
        return AnomalyType.HALLUCINATION, "AI 表示不理解（可能上下文丢失）"
    
    # 检测代码质量
    if "TODO" in record.response_content or "FIXME" in record.response_content:
        return AnomalyType.HALLUCINATION, "AI 生成了 TODO/FIXME 标记"
    
    return None
```

---

## 💡 最佳实践

### 1. 日常使用流程

```bash
# 开发新功能后，运行相关场景测试
python test_executor.py --scenario code_generation --max-rounds 5

# 如果发现问题，查看详情
python anomaly_analyzer.py --latest

# 修正代码后，重新测试
python test_executor.py --scenario code_generation --max-rounds 5
```

### 2. 回归测试

```bash
# 发布前运行完整测试
python batch_runner.py --all --max-rounds 3 --retry

# 分析结果
python anomaly_analyzer.py --trend
```

### 3. 持续监控

```bash
# 添加到定时任务（如每小时运行一次关键场景）
*/1 * * * * cd /path/to/backend && python tests/monitoring/batch_runner.py \
    --scenarios code_generation,knowledge_query \
    --max-rounds 2 \
    --auto >> tests/monitoring/logs/cron.log 2>&1
```

---

## ⚠️ 注意事项

1. **成本**: 每次测试消耗真实 Token，批量测试前先小范围验证
2. **超时**: 每个测试默认 60 秒超时，避免长时间挂起
3. **状态**: 测试会创建真实对话，记得定期清理
4. **并发**: 目前串行执行，避免并发导致的结果混淆

---

## 🔧 故障排查

### 测试连接失败
```bash
# 检查后端服务
curl http://localhost:20160/api/health

# 检查 API 地址
export EVOLOOP_API_URL=http://localhost:20160
```

### LLM 无响应
```bash
# 检查 API Key
export OPENAI_API_KEY=sk-xxx

# 检查模型可用性
python -c "import openai; print(openai.Model.list())"
```

### 报告为空
```bash
# 检查目录权限
mkdir -p tests/monitoring/reports
chmod 755 tests/monitoring/reports
```

---

## 📈 扩展计划

- [ ] Web 监控仪表板（实时查看测试状态）
- [ ] 自动回归测试（CI/CD 集成）
- [ ] 异常模式学习（基于历史数据预测）
- [ ] 多模型对比测试（GPT-4 vs Claude vs 本地模型）
- [ ] 性能基准测试（响应时间、Token 效率）
