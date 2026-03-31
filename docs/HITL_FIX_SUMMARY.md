# HITL 取消功能修复总结

## 问题描述

取消 HITL（人工介入）请求后，前端聊天界面的状态没有正确更新：
- HITL 卡片仍然显示在界面上
- 输入框仍然被禁用
- 用户无法继续对话

## 根本原因

### 1. 后端状态不一致
```python
# cache_services.py 存储的状态
"status": "running"  # ❌ 错误

# activity.py 发送的事件  
StatusEvent(status="idle")  # 正确
```

Cache 状态与发送的事件不一致，导致前端刷新后得到错误的状态。

### 2. 前后端状态语义不匹配
前端乐观更新使用 `status="running"`，但后端实际发送 `status="idle"`。

### 3. 缺乏安全网机制
- 前端没有错误回滚机制
- 前端没有超时保护
- 状态变更时没有清理残留的 `humanRequest`

## 修复内容

### 后端修复

**文件**: `backend/app/services/cache_services.py:287`

```python
# 修改前
"status": "running",

# 修改后  
"status": "idle",  # HITL cleared, agent not yet resumed
```

**理由**:
- 与 `activity.py` 发送的 `StatusEvent(status="idle")` 保持一致
- 语义正确：`clear_human_request` 只是清理 HITL，Agent 尚未恢复执行
- 安全性：如果 `_cancel_and_resume` 失败，状态是 `idle` 而非错误的 `running`

### 前端修复

**文件 1**: `frontend/packages/desktop/src/stores/chatStore.ts:402`

```typescript
// 修改前
set({ status: "running", humanRequest: null })

// 修改后
set({ status: "idle", humanRequest: null })
```

**文件 2**: 添加错误回滚和超时保护 (lines 397-426)

```typescript
cancelHumanRequest: async (reason?: string) => {
    // 保存之前的状态用于回滚
    const previousStatus = get().status
    const previousHumanRequest = get().humanRequest

    // 乐观更新
    set({ status: "idle", humanRequest: null })

    try {
        await AgentService.cancelHitlRequest({...})
        
        // 超时保护：5秒后检查状态
        setTimeout(() => {
            if (current.status === "interrupted" && current.humanRequest) {
                set({ status: "idle", humanRequest: null })
            }
        }, 5000)
        
    } catch (error) {
        // 回滚乐观更新
        set({ status: previousStatus, humanRequest: previousHumanRequest })
    }
}
```

**文件 3**: 添加 `_updateStatus` 安全网 (lines 646-658)

```typescript
// HITL Safety Net 1: 离开 interrupted 状态时清理 humanRequest
if (prevStatus === "interrupted" && normalizedStatus !== "interrupted") {
    set({ status: normalizedStatus, humanRequest: null })
    return
}

// HITL Safety Net 2: 状态不是 interrupted 但 humanRequest 存在，清理它
if (normalizedStatus !== "interrupted" && currentHumanRequest) {
    set({ status: normalizedStatus, humanRequest: null })
    return
}
```

## 修复后的状态流转

```
用户点击取消
    ↓
后端: clear_human_request()
    ├─ Cache: status="idle"        ✅ (修复后)
    └─ 事件: StatusEvent("idle")    ✅ (已一致)
    ↓
前端: 乐观更新 status="idle"       ✅ (修复后)
    ↓
后端: _cancel_and_resume() 启动
    ├─ start_run(): status="running"
    └─ 事件: StatusEvent("running")
    ↓
前端: 状态 running，显示停止按钮
    ↓
Agent 完成: end_run(): status="idle"
    ↓
前端: 状态 idle，输入框完全可用
```

## 测试验证

### 测试场景

| 场景 | 步骤 | 预期结果 |
|------|------|---------|
| 正常取消 | 1. 触发 HITL<br>2. 点击取消 | 卡片消失 → 状态 idle → 停止按钮 → 完成 |
| 取消后刷新 | 1. 取消 HITL<br>2. 刷新页面 | 显示正确状态（running 或 idle） |
| 网络故障 | 1. 断开网络<br>2. 点击取消 | 5秒后强制重置，提示错误 |
| API 失败 | Mock 失败响应 | 状态回滚，卡片重新显示 |

### 验证命令

```bash
# 后端语法检查
cd backend && python3 -m py_compile app/services/cache_services.py

# 修复验证
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop && python3 test_hitl_fix.py
```

## 监控日志

修复后，浏览器控制台会输出以下日志：

```
[HITL Safety] Cleared humanRequest on status change: interrupted -> running
[HITL Safety] Orphan humanRequest detected, clearing. Status: idle
[HITL Cancel] Timeout: state stuck in interrupted, forcing reset
```

## 回滚策略

如果修复导致问题，可以单独回滚：

### 回滚后端
```python
# cache_services.py:287
"status": "running",  # 改回原来的值
```

### 回滚前端
```typescript
// chatStore.ts:402
set({ status: "running", humanRequest: null })  // 改回原来的值

// 删除新增的安全网代码
```

## 相关文件

| 文件 | 修改类型 | 行数 |
|------|---------|------|
| `backend/app/services/cache_services.py` | 修改 | 287 |
| `frontend/packages/desktop/src/stores/chatStore.ts` | 修改 | 397-426, 646-658 |

## 后续优化建议

1. **添加后端超时机制**: HITL 请求应该在一定时间后自动超时
2. **状态同步校验**: 定期同步前后端状态，检测不一致
3. **更细粒度的错误处理**: 区分网络错误和业务错误
