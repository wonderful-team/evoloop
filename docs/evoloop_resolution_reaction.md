# EvoLoop 解决方案生成后的反应机制

## 核心问题

**"那生成了更精准的解决方案以后，EvoLoop 会如何做反应？"**

答案：EvoLoop **不直接执行**，而是通过闭环反馈机制 **验证结果 → 更新知识 → 决定下一步**。

---

## 完整反应流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EvoLoop 生成解决方案后                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. 传递方案                                                                │
│     └── 通过 MCP / HTTP API 发送给 Crawler                                  │
│         {                                                                   │
│           "action": "update_selector",                                      │
│           "config_updates": {"selector": "#new-id"},                        │
│           "confidence": 0.9,                                                │
│           "requires_manual": false                                          │
│         }                                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  2. 等待 Crawler 执行                                                       │
│     └── 异步等待，不阻塞其他任务                                            │
│     └── 设置超时（如 5 分钟）                                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  3. 接收执行结果（关键反馈节点）                                            │
│     └── Crawler 上报执行结果到 EvoLoop                                      │
│         POST /api/v1/crawler/resolutions/executions                         │
│         {                                                                   │
│           "error_id": "err_001",                                            │
│           "resolution_id": "res_001",                                       │
│           "status": "success" | "partial_success" | "failed",              │
│           "result": {...},          ← 执行返回的数据                        │
│           "duration_ms": 5000,                                              │
│           "config_applied": {...},  ← 实际应用的配置                        │
│           "retry_count": 0                                                  │
│         }                                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  4. EvoLoop 验证执行结果（核心决策点）                                        │
│                                                                             │
│     验证维度：                                                              │
│     ├── 状态检查：success / partial / failed                               │
│     ├── 数据完整性：content_length, screenshot_size                        │
│     ├── 错误信息：是否有新错误                                              │
│     ├── 性能指标：duration_ms 是否在合理范围                               │
│     └── 重试次数：是否超过阈值                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
            ┌───────────┐     ┌───────────┐     ┌───────────┐
            │ 完全成功  │     │ 部分成功  │     │ 执行失败  │
            │ (success) │     │ (partial) │     │ (failed)  │
            └─────┬─────┘     └─────┬─────┘     └─────┬─────┘
                  │                 │                 │
                  ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  5. 根据验证结果做出不同反应                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 四种典型反应场景

### 场景 1: 执行完全成功 ✅

```python
# EvoLoop 验证逻辑
if result.status == "success" and len(content) > 1000:
    verification = {
        "verified": True,
        "status": "success",
        "success_criteria_met": ["execution_completed", "content_extracted"],
        "failed_criteria": [],
    }
```

**EvoLoop 反应：**

| 动作 | 说明 |
|------|------|
| ✅ 更新知识库 | 标记方案为有效，成功率 +1 |
| ✅ 记录经验 | "使用 #content 选择器比 .content 更稳定" |
| ✅ 反馈给 Crawler | `{should_continue: true, message: "方案验证通过"}` |
| ✅ 继续执行 | 任务完成，无需进一步干预 |

---

### 场景 2: 部分成功 ⚠️

```python
# 内容提取了但较少，可能页面未完全加载
if result.status == "success" and len(content) < 500:
    verification = {
        "verified": True,
        "status": "partial",
        "success_criteria_met": ["execution_completed"],
        "failed_criteria": ["content_too_short"],
    }
```

**EvoLoop 反应：**

| 动作 | 说明 |
|------|------|
| ✅ 记录部分成功 | 方案有效但需要优化 |
| ✅ 生成改进建议 | "增加 wait_until='networkidle'" |
| ✅ 反馈给 Crawler | `{should_continue: true, suggested_improvement: "..."}` |
| ⏳ 可选：优化方案 | 下次遇到类似问题时自动增加等待时间 |

---

### 场景 3: 执行失败 → 生成新方案 🔄

```python
# 同样的错误再次发生，说明方案无效
if "same_error" in result.error:
    verification = {
        "verified": False,
        "status": "failed",
        "requires_new_resolution": True,
        "next_action": "generate_new_resolution",
    }
```

**EvoLoop 反应：**

| 动作 | 说明 |
|------|------|
| ❌ 标记方案无效 | 避免将来再次使用 |
| 🔄 触发重新分析 | 调用 LLM，提供更多上下文 |
| 📝 记录教训 | "CSS 选择器失效，尝试 XPath" |
| ⏳ 生成新方案 | `{"action": "try_xpath", "selector": "//div[@class='main']"}` |
| 📤 下发新方案 | 通过 API 推送给 Crawler |
| 🔄 重新执行 | Crawler 应用新方案重试 |

**迭代流程：**

```
第1次: CSS 选择器 .content → 失败
         ↓
    EvoLoop: "尝试使用 id 选择器"
         ↓
第2次: #content → 失败（元素不存在）
         ↓
    EvoLoop: "尝试 XPath"
         ↓
第3次: //div[@class='main'] → 成功！
         ↓
    EvoLoop: 记录成功方案，更新知识库
```

---

### 场景 4: 多次失败 → 升级人工 🚨

```python
# 已经重试 3 次仍然失败
if retry_count >= 3 and result.status == "failed":
    verification = {
        "verified": False,
        "status": "escalated",
        "requires_manual": True,
        "escalation_reason": "Multiple resolution attempts failed",
    }
```

**EvoLoop 反应：**

| 动作 | 说明 |
|------|------|
| 🚨 停止自动重试 | 避免无限循环 |
| 📋 生成人工任务 | `{type: "solve_captcha", screenshot: "...", priority: "high"}` |
| 📧 通知相关人员 | 发送邮件/Slack 通知 |
| ⏸️ 暂停任务 | 等待人工介入 |
| ✅ 人工解决后 | 从人工方案中学习，更新知识库 |

---

## 代码实现：EvoLoop 验证逻辑

```python
# /evoloop/backend/app/api/routes/crawler_resolutions.py

async def _verify_execution_result(report: ExecutionResultReport) -> VerificationOutcome:
    """
    验证执行结果并决定下一步行动
    """
    outcome = VerificationOutcome()

    # 1. 基础状态检查
    if report.status == "success":
        outcome.success_criteria_met.append("execution_completed")
    else:
        outcome.failed_criteria.append("execution_failed")

    # 2. 数据完整性检查
    if report.result and report.result.get("content_length", 0) > 1000:
        outcome.success_criteria_met.append("content_extracted")
    else:
        outcome.failed_criteria.append("content_too_short")

    # 3. 错误分析
    if report.error:
        outcome.failed_criteria.append(f"error: {report.error}")

        # 同类错误 → 方案无效
        if "same_error" in report.error.lower():
            outcome.requires_new_resolution = True
            outcome.next_action = "generate_new_resolution"

    # 4. 重试次数检查
    if report.retry_count >= 3:
        outcome.failed_criteria.append("max_retries_exceeded")
        outcome.requires_new_resolution = False  # 不再尝试自动方案
        outcome.next_action = "escalate_to_manual"

    # 5. 综合判定
    if len(outcome.success_criteria_met) >= 2 and len(outcome.failed_criteria) == 0:
        # ✅ 完全成功
        outcome.verified = True
        outcome.status = "success"
        outcome.feedback_message = "方案验证通过，已记录到知识库"
        await _update_knowledge_base_success(report.resolution_id)

    elif outcome.requires_new_resolution and report.retry_count < 3:
        # 🔄 需要新方案
        outcome.status = "failed"
        outcome.feedback_message = "当前方案无效，正在生成新方案..."
        await _trigger_new_resolution_analysis(report.error_id, report.resolution_id)

    elif report.retry_count >= 3:
        # 🚨 升级人工
        outcome.status = "escalated"
        outcome.feedback_message = "自动解决方案耗尽，需要人工介入"
        await _create_manual_intervention_task(report)

    return outcome
```

---

## 反馈给 Crawler 的数据结构

```python
{
    "execution_id": "exec_001",
    "verified": True | False,
    "verification_status": "success" | "partial" | "failed" | "escalated",

    # 验证详情
    "success_criteria_met": ["execution_completed", "content_extracted"],
    "failed_criteria": [],

    # 后续决策
    "requires_new_resolution": False,
    "suggested_next_action": None,

    # 知识库更新
    "knowledge_base_updated": True,
    "lessons_learned": "使用 id 选择器更稳定",

    # 给 Crawler 的具体反馈
    "feedback_for_crawler": {
        "should_continue": True,           # 是否继续执行
        "retry_allowed": False,            # 是否允许再次重试
        "escalate_to_manual": False,       # 是否升级人工
        "wait_for_new_resolution": False,  # 是否等待新方案
        "message": "方案验证通过",          # 人类可读消息
        "suggested_improvement": None,     # 改进建议（部分成功时）
    }
}
```

---

## 知识库学习机制

```python
# 成功案例学习
async def _learn_from_success(resolution_id: str, execution_data: dict):
    """从成功案例中提取经验"""

    # 更新成功率统计
    await increment_success_count(resolution_id)

    # 记录方案特征
    await save_resolution_pattern(
        error_type=execution_data["error_type"],
        url_pattern=execution_data["url"],
        resolution_action=execution_data["resolution_action"],
        config_updates=execution_data["config_applied"],
        effectiveness_score=calculate_effectiveness(execution_data),
    )

    # 生成自然语言经验
    lesson = await generate_lesson_learned(execution_data)
    # 例如: "对于 example.com 的 timeout 错误，增加超时到 30s 有效"

    await save_lesson(lesson)
```

```python
# 失败案例学习
async def _learn_from_failure(resolution_id: str, failure_data: dict):
    """从失败案例中避免重复错误"""

    # 标记方案为无效
    await mark_resolution_invalid(resolution_id)

    # 记录失败原因
    await save_failure_pattern(
        resolution_id=resolution_id,
        error_type=failure_data["error_type"],
        failure_reason=failure_data["error"],
    )

    # 下次生成方案时排除无效方案
    await update_resolution_blacklist(
        error_pattern=failure_data["error_pattern"],
        invalid_action=failure_data["resolution_action"],
    )
```

---

## 完整闭环时序图

```
Crawler                           EvoLoop
  │                                 │
  │──── 1. 执行任务 ──────────────▶│
  │                                 │
  │◀─── 2. 任务失败 ───────────────│
  │                                 │
  │──── 3. 上报详细错误 ──────────▶│
  │     (截图、快照、历史)          │
  │                                 │
  │                                 │──── 4. LLM 分析错误
  │                                 │
  │                                 │──── 5. 生成解决方案
  │                                 │
  │◀─── 6. 下发解决方案 ───────────│
  │     (config_updates)            │
  │                                 │
  │──── 7. 应用方案并重试 ────────▶│
  │                                 │
  │◀─── 8. 执行成功 ───────────────│
  │                                 │
  │──── 9. 上报执行结果 ──────────▶│
  │     (status, result, duration)  │
  │                                 │
  │                                 │──── 10. 验证结果 ✅
  │                                 │
  │                                 │──── 11. 更新知识库
  │                                 │     (成功率 +1)
  │                                 │
  │◀─── 12. 反馈验证结果 ──────────│
  │     "方案验证通过"              │
  │                                 │
  ✓ 任务完成                        ✓ 知识积累
```

---

## 总结

**EvoLoop 生成解决方案后的反应可以概括为：**

1. **不直接干预执行** — Crawler 独立应用方案
2. **等待执行结果** — 通过 API 异步接收反馈
3. **多维度验证** — 状态、数据、错误、性能
4. **四种决策路径** — 成功/部分成功/重试/人工
5. **持续学习** — 成功案例入知识库，失败案例避免重复

**核心设计原则：**

- **闭环反馈**：每个方案都有验证结果
- **自我改进**：从成功和失败中学习
- **优雅降级**：自动 → 重试 → 人工
- **知识积累**：经验沉淀为可复用方案
