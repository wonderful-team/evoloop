# 配额耗尽错误处理设计

## 当前实现
- 错误类型：`failed`
- 用户操作：必须点击 Resume
- 消息记录：存入数据库作为 ai 消息

## 建议改进

### 1. 新增错误状态 `quota_exhausted`

```python
# activity_monitor.py
await activity_monitor.end_run(thread_id, "quota_exhausted")
```

### 2. 前端特殊处理

当检测到 `status="quota_exhausted"` 时：
- 显示醒目提示横幅（而非普通消息）
- 提供"检查配额"按钮跳转 dashboard
- 用户发送新消息时自动 Resume

### 3. Backend 自动恢复

```python
# 用户发送新消息时
if current_status == "quota_exhausted":
    # 自动 Resume，无需用户点击
    inputs["is_retry"] = True
    await graph.ainvoke(inputs, config)
```

### 4. 消息优化

不要将配额错误作为 ai 消息，而是：
- 使用 `action_type="system_notification"`
- 或 WebSocket 推送临时通知
- 避免污染对话历史

## 实现优先级

P1：前端显示优化（明确提示配额不足）
P2：续费后自动恢复（发送消息自动 Resume）
P3：不污染对话历史（system_notification）

## 参考实现

```python
# background_agent.py 改进

except RateLimitError as e:
    if "quota_exhausted" in str(e):
        # 特殊处理配额错误
        await activity_monitor.end_run(thread_id, "quota_exhausted")
        await _persist_quota_notification(thread_id, project_id)
        
        # 发送 WebSocket 通知（即时显示，不存数据库）
        await websocket_manager.send_notification(
            thread_id=thread_id,
            type="quota_exhausted",
            message="LLM 配额已耗尽，请续费后继续使用"
        )
    else:
        # 其他 rate limit 按原逻辑处理
        raise
```

## 前端 Mockup

```
┌─────────────────────────────────────┐
│ ⚠️  LLM 配额已耗尽                    │
│                                     │
│ 您的账户 LLM 配额已使用完毕。          │
│ 请联系管理员增加配额，或前往 Dashboard │
│ 查看使用情况。                        │
│                                     │
│ [查看配额] [已续费，继续对话]          │
└─────────────────────────────────────┘
```
