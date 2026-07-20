# 两级 LLM 策略：本地闪电 + 云端 Gateway

### 1.1 目标

降低语音链路首句 TTS 延迟。当前 Agent 图全部走 EvoLoop Gateway（`deepseek-chat`），首次 LLM 调用（Supervisor）延迟 ~2s。Supervisor 的决策分两种情况：

- **直接回答**（问候、简单 Q&A、状态查询）：不需要云端推理质量，但占首 token 延迟大头
- **派 Worker**（复杂任务）：需要云端推理质量，`route_to(worker)` 本身就是切换机制

### 1.2 策略

```
if LIGHTNING_MODE 已配置（非 "none"）and LIGHTNING_BASE_URL 非空:
    Supervisor → 本地闪电模型（首 token ~500ms）
    Worker     → inputs.model（默认云端 deepseek-chat）
    Finish     → inputs.model（默认云端 deepseek-chat）
else:
    全部 → inputs.model（默认）
```

| 节点 | 模型 | 位置 | 延迟 | 推理质量 |
|------|------|------|------|---------|
| Supervisor | 闪电模型（同 `LIGHTNING_LLM_MODEL`） | 本地 LM Studio | ~500ms | 够用（简单问答、路由决策） |
| Worker | 主要模型（`LLM_MODEL`） | EvoLoop Gateway | ~2s | 高（多步任务、工具调用） |
| Finish | 主要模型（`LLM_MODEL`） | EvoLoop Gateway | ~2s | 高（质量门、审计） |

本地闪电模型支持工具调用（Qwen3-4B 级别），知道自己的模型能力边界——对于复杂场景：
- 无法 100% 确定工具选择的任务 → route_to(worker)
- 多步操作 → route_to(worker)
- 不熟悉的知识领域 → route_to(worker)

这样在首 token 速度收益的同时，不牺牲回答质量。

### 1.3 配置来源

不硬编码模型名和地址。全部读取用户已有配置：

| 配置项 | Supervisor 用 | Worker/Finish 用 |
|--------|--------------|-----------------|
| `LIGHTNING_MODE` | 非 `none` 时启用本地 | - |
| `LIGHTNING_LLM_MODEL` | ✅ 本地模型名 | - |
| `LIGHTNING_BASE_URL` | ✅ 本地地址（如 `http://127.0.0.1:1234/v1`） | - |
| `LLM_MODEL` | - | ✅ 云端模型名 |
| `LLM_CONFIG_TYPE` | - | ✅ platform（走 Gateway） |

闪电模式关闭（`LIGHTNING_MODE=none`）时，全部走默认模型，行为不变。

### 1.4 实现

| 文件 | 变更 |
|------|------|
| `runner.py` | 检测闪电模式配置，写入 `config.configurable.lightning_model`、`lightning_base_url`、`worker_model` |
| `LLMFactory.create_llm()` | `base_url` 非空时走 `_create_direct_llm`（已有函数，加分支） |
| `BaseAgentNode.run()` | Supervisor 用 `lightning_model`；Worker 和 Finish 用 `worker_model` |
| `supervisor_builder.py` | 增加 `is_lightning` 模板变量 |
| `supervisor.prompt.j2` | `{% if is_lightning %}` 插入模型自知规则 |
| 新建 `lightning_behavior.j2` | 本地模型的模型自知规则片段（文字链路用） |
| `voice_behavior.j2` | 加一条模型自知规则（语音链路额外约束） |
| `finish.prompt.j2` | 清理第 8 行 `learn_from_trace` 引用（工具已删除） |

### 1.5 预期效果

| 指标 | 改前（全部云端） | 改后（本地+云端） |
|------|----------------|-----------------|
| 首句 TTS (TTFB) | ~2s（deepseek-chat） | ~500ms（本地闪电模型） |
| 直接回答质量 | deepseek-chat | Qwen3-4B（简单场景够用） |
| Worker 推理质量 | deepseek-chat | deepseek-chat（不变） |
| Finish 审计质量 | deepseek-chat | deepseek-chat（不变） |
| 闪电模式关闭时 | — | 全部走默认，行为不变 |

---

